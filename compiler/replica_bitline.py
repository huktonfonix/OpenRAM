import debug
import design
from tech import drc
from pinv import pinv
from contact import contact
from bitcell_array import bitcell_array
from nor_2 import nor_2
from ptx import ptx
from vector import vector
from globals import OPTS

class replica_bitline(design.design):
    """
    Generate a module that simulate the delay of control logic 
    and bit line charging.
    Used for memory timing control
    """

    def __init__(self, rows, name="replica_bitline"):
        design.design.__init__(self, name)

        g = reload(__import__(OPTS.config.delay_chain))
        self.mod_delay_chain = getattr(g, OPTS.config.delay_chain)

        g = reload(__import__(OPTS.config.replica_bitcell))
        self.mod_replica_bitcell = getattr(g, OPTS.config.replica_bitcell)

        c = reload(__import__(OPTS.config.bitcell))
        self.mod_bitcell = getattr(c, OPTS.config.bitcell)

        for pin in ["en", "out", "vdd", "gnd"]:
            self.add_pin(pin)
        self.rows = rows

        self.create_modules()
        self.calculate_module_offsets()
        self.add_modules()
        self.route()
        #self.offset_all_coordinates()

        self.DRC_LVS()

    def calculate_module_offsets(self):
        """ Calculate all the module offsets """
        
        # These aren't for instantiating, but we use them to get the dimensions
        self.poly_contact = contact(layer_stack=("poly", "contact", "metal1"))
        self.m1m2_via = contact(layer_stack=("metal1", "via1", "metal2"))
        self.m2m3_via = contact(layer_stack=("metal2", "via2", "metal3"))

        # M1/M2 routing pitch is based on contacted pitch
        m1_pitch = max(self.m1m2_via.width,self.m1m2_via.height) + drc["metal2_to_metal2"]
        m2_pitch = max(self.m2m3_via.width,self.m2m3_via.height) + drc["metal3_to_metal3"]
        

        # delay chain will be rotated 90, so move it over a width
        # we move it up a inv height just for some routing room
        self.rbl_inv_offset = vector(self.delay_chain.height, self.inv.width)
        # access TX goes right on top of inverter, leave space for an inverter which is
        # about the same as a TX. We'll need to add rails though.
        self.access_tx_offset = vector(1.25*self.inv.height,self.rbl_inv_offset.y) + vector(0,2*self.inv.width)
        self.delay_chain_offset = self.rbl_inv_offset + vector(0,4*self.inv.width)

        # Replica bitline and such are not rotated
        self.bitcell_offset = self.rbl_inv_offset + vector(4*m2_pitch, 0)

        self.rbl_offset = self.bitcell_offset + vector(0, self.bitcell.height)

        
        self.height = self.rbl_offset.y + self.rbl.height 
        self.width = self.rbl_offset.x + self.bitcell.width


    def create_modules(self):
        """ Create modules for later instantiation """
        self.bitcell = self.mod_replica_bitcell()
        self.add_mod(self.bitcell)

        # This is the replica bitline load column that is the height of our array
        self.rbl = bitcell_array(name="bitline_load", cols=1, rows=self.rows)
        self.add_mod(self.rbl)
        
        self.delay_chain = self.mod_delay_chain([1, 1, 1])
        self.add_mod(self.delay_chain)

        self.inv = pinv(nmos_width=drc["minwidth_tx"])
        self.add_mod(self.inv)

        self.access_tx = ptx(tx_type="pmos")
        self.add_mod(self.access_tx)

    def add_modules(self):
        """ Add all of the module instances in the logical netlist """
        # This is the threshold detect inverter on the output of the RBL
        self.add_inst(name="rbl_inv",
                      mod=self.inv,
                      offset=self.rbl_inv_offset,
                      rotate=90,
                      mirror=MY)
        self.connect_inst(["bl[0]", "out", "vdd", "gnd"])

        self.add_inst(name="rbl_access_tx",
                      mod=self.access_tx,
                      offset=self.access_tx_offset,
                      rotate=90)
        # D, G, S, B
        self.connect_inst(["vdd", "delayed_en", "bl[0]", "vdd"])

        self.add_inst(name="delay_chain",
                      mod=self.delay_chain,
                      offset=self.delay_chain_offset,
                      rotate=90)
        self.connect_inst(["en", "delayed_en", "vdd", "gnd"])

        self.add_inst(name="bitcell",
                      mod=self.bitcell,
                      offset=self.bitcell_offset)
        self.connect_inst(["bl[0]", "br[0]", "delayed_en", "vdd", "gnd"])

        self.add_inst(name="load",
                      mod=self.rbl,
                      offset=self.rbl_offset)
        self.connect_inst(["bl", "br"] + ["gnd"]*self.rows + ["vdd", "gnd"])
        
        #self.expan_the_well_to_rbl_inv()

    def expan_the_well_to_rbl_inv(self):
        width = self.rbl_inv_offset.x - self.access_tx_offset.x + self.inv.width
        well_offset = self.access_tx_offset - vector(self.access_tx.width, 0)
        for layer in ["nwell", "vtg"]:
            self.add_rect(layer=layer,
                          offset=well_offset,
                          width=width,
                          height= 2*self.access_tx.width)

    def route(self):
        """connect modules together"""

        self.route_gnd()
        self.route_vdd()

 





    def route_vdd(self):
        # Add a rail in M1 from bottom to two along delay chain
        inv_vdd_offset = self.inv.get_pin("vdd").ll().rotate_scale(-1,1)
        vdd_start = self.rbl_inv_offset.scale(1,0) + inv_vdd_offset
        # It is the height of the entire RBL and bitcell
        self.add_layout_pin(text="vdd",
                            layer="metal2",
                            offset=vdd_start,
                            width=-drc["minwidth_metal2"],
                            height=self.rbl.height+self.bitcell.height+self.inv.width)

        # Connect the vdd pins directly to vdd
        vdd_pins = self.rbl.get_pin("vdd")
        for pin in vdd_pins:
            offset = vector(vdd_start.x,self.rbl_offset.y+pin.ly()) - vector(drc["minwidth_metal2"],0)
            self.add_rect(layer="metal1",
                          offset=offset,
                          width=self.rbl_offset.x-vdd_start.x,
                          height=drc["minwidth_metal2"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=offset)

        # Add via for the delay chain
        offset = self.delay_chain_offset + inv_vdd_offset + vector(0,self.delay_chain.width) - vector(drc["minwidth_metal2"],0)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)
        # Add via for the inverter
        offset = self.rbl_inv_offset + inv_vdd_offset + vector(0,self.inv.width) - vector(drc["minwidth_metal2"],0)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)
            
    
    def route_gnd(self):
        # Add a rail in M1 from bottom to two along delay chain
        gnd_start = self.rbl_inv_offset.scale(1,0) + self.inv.get_pin("gnd").ll().rotate_scale(1,1)
        # It is the height of the entire RBL and bitcell
        self.add_layout_pin(text="gnd",
                            layer="metal2",
                            offset=gnd_start,
                            width=drc["minwidth_metal2"],
                            height=self.rbl.height+self.bitcell.height+self.inv.width)
                      
        # Connect the WL pins directly to gnd
        for row in range(self.rows):
            wl = "wl[{}]".format(row)
            pin = self.rbl.get_pin(wl)
            offset = vector(gnd_start.x,self.rbl_offset.y+pin.ly())
            self.add_rect(layer="metal1",
                          offset=offset,
                          width=self.rbl_offset.x-gnd_start.x,
                          height=drc["minwidth_metal2"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=offset)

      # Add via for the delay chain
        offset = self.delay_chain_offset+vector(-0.5*drc["metal1_to_metal1"],self.delay_chain.width)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)
        # Add via for the inverter
        offset = self.rbl_inv_offset+vector(-0.5*drc["metal1_to_metal1"],self.inv.width)        
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)
        

    def route_loads(self,vdd_offset):
        """ Route all  all the load word line to gnd """
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=vdd_offset,
                     mirror="MX")
        gnd_offset = self.delay_chain_offset + vector([drc["minwidth_metal1"]]*2).scale(-0.5,0.5)
        for i in range(self.rows):
            wl_offset = self.replica_bitline_offset + self.bitline_load.get_pin("wl[{}]".format(i)).ll().scale(0,1)
            mid = vector(self.delay_chain_offset.x  + 6*drc["minwidth_metal2"], gnd_offset.y)
            self.add_wire(layers=("metal1", "via1", "metal2"), 
                          coordinates=[gnd_offset, mid, wl_offset])
            if i % 2 == 0:
                load_vdd_offset = self.replica_bitline_offset + self.bitline_load.get_pin("vdd")[0].ll()
                mid = vector(vdd_offset.x, load_vdd_offset.y)
                self.add_wire(layers=("metal1", "via1", "metal2"), 
                              coordinates=[vdd_offset, mid, load_vdd_offset])

    def route_replica_cell(self,vdd_offset):
        """ Route vdd gnd to the replica cell """
        # connect vdd
        RC_vdd = self.replica_bitline_offset + self.bitcell.get_pin("vdd").ll().scale(1,-1)
        mid = vector(vdd_offset.x, RC_vdd.y)
        # Note the inverted stacks
        self.add_wire(layers=("metal1", "via1", "metal2"), 
                      coordinates=[vdd_offset, mid, RC_vdd])

        gnd_offset = self.rbl_inv_offset - vector(self.inv.width, 0)
        load_gnd = self.replica_bitline_offset + vector(self.bitcell.get_pin("gnd").lx(), 
                                                        self.bitline_load.height)
        mid = vector(load_gnd.x, gnd_offset.y)
        self.add_wire(layers=("metal1", "via1", "metal2"), 
                      coordinates=[gnd_offset, mid, load_gnd])

        load_gnd = self.replica_bitline_offset + vector(0, self.bitline_load.height)
        mid = vector(load_gnd.x, gnd_offset.y)
        self.add_wire(("metal1", "via1", "metal2"), [gnd_offset, mid, load_gnd])
