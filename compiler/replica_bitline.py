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
        self.poly_contact_offset = vector(0.5*self.poly_contact.width,0.5*self.poly_contact.height)
        self.m1m2_via = contact(layer_stack=("metal1", "via1", "metal2"))
        self.m2m3_via = contact(layer_stack=("metal2", "via2", "metal3"))

        # M1/M2 routing pitch is based on contacted pitch
        self.m1_pitch = max(self.m1m2_via.width,self.m1m2_via.height) + max(drc["metal1_to_metal1"],drc["metal2_to_metal2"])
        self.m2_pitch = max(self.m2m3_via.width,self.m2m3_via.height) + max(drc["metal2_to_metal2"],drc["metal3_to_metal3"])
        

        # delay chain will be rotated 90, so move it over a width
        # we move it up a inv height just for some routing room
        self.rbl_inv_offset = vector(self.delay_chain.height, self.inv.width)
        # access TX goes right on top of inverter, leave space for an inverter which is
        # about the same as a TX. We'll need to add rails though.
        self.access_tx_offset = vector(1.25*self.inv.height,self.rbl_inv_offset.y) + vector(0,2*self.inv.width)
        self.delay_chain_offset = self.rbl_inv_offset + vector(0,4*self.inv.width)

        # Replica bitline and such are not rotated, but they must be placed far enough
        # away from the delay chain/inverter with space for two M2 tracks
        self.bitcell_offset = self.rbl_inv_offset + vector(2*self.m2_pitch+drc["metal2_to_metal2"], 0) + vector(0, self.bitcell.height)

        self.rbl_offset = self.bitcell_offset

        
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
                      offset=self.rbl_inv_offset+vector(0,self.inv.width),
                      rotate=270,
                      mirror="MX")
        self.connect_inst(["bl[0]", "out", "vdd", "gnd"])

        self.add_inst(name="rbl_access_tx",
                      mod=self.access_tx,
                      offset=self.access_tx_offset,
                      rotate=90)
        # D, G, S, B
        self.connect_inst(["vdd", "delayed_en", "bl[0]", "vdd"])
        # add the well and poly contact

        self.add_inst(name="delay_chain",
                      mod=self.delay_chain,
                      offset=self.delay_chain_offset,
                      rotate=90)
        self.connect_inst(["en", "delayed_en", "vdd", "gnd"])

        self.add_inst(name="bitcell",
                      mod=self.bitcell,
                      offset=self.bitcell_offset,
                      mirror="MX")
        self.connect_inst(["bl[0]", "br[0]", "delayed_en", "vdd", "gnd"])

        self.add_inst(name="load",
                      mod=self.rbl,
                      offset=self.rbl_offset)
        self.connect_inst(["bl", "br"] + ["gnd"]*self.rows + ["vdd", "gnd"])
        



    def route(self):
        """ Connect all the signals together """
        self.route_gnd()
        self.route_vdd()
        self.route_access_tx()


    def route_access_tx(self):
        # GATE ROUTE
        # 1. Add the poly contact and nwell enclosure
        # Determines the y-coordinate of where to place the gate input poly pin
        # (middle in between the pmos and nmos)
        poly_offset = self.access_tx_offset + vector(0, self.access_tx.poly_positions[0].x)
        contact_offset = poly_offset + vector(self.poly_contact.width, -(drc["metal1_extend_contact"]))
        self.add_contact(layers=("poly", "contact", "metal1"),
                         offset=contact_offset)
        self.add_rect(layer="poly",
                      offset=poly_offset,
                      width=contact_offset.x-poly_offset.x,
                      height=drc["minwidth_poly"])
        nwell_offset = self.rbl_inv_offset + vector(-self.inv.height,self.inv.width)
        self.add_rect(layer="nwell",
                      offset=nwell_offset,
                      width=0.5*self.inv.height,
                      height=self.delay_chain_offset.y-nwell_offset.y)

        # 2. Route delay chain output to access tx gate
        delay_en_offset = self.delay_chain_offset+self.delay_chain.get_pin("out").lc().rotate_scale(-1,1)
        delay_en_mid_offset = vector(delay_en_offset.x,contact_offset.y)
        self.add_path("metal1", [delay_en_offset,delay_en_mid_offset,contact_offset])


        # 3. Route the mid-point of previous route to the bitcell WL
        # route bend of previous net to bitcell WL
        wl_offset = self.bitcell_offset - self.bitcell.get_pin("WL").lc()
        wl_mid = vector(delay_en_mid_offset.x,wl_offset.y)
        self.add_path("metal1", [delay_en_mid_offset, wl_mid, wl_offset])

        # SOURCE ROUTE
        # Route the source to the vdd rail
        source_offset = self.access_tx_offset + self.access_tx.active_contact_positions[1].rotate_scale(-1,1) \
                        + self.poly_contact_offset.rotate_scale(-1,1)
        vdd_pin_offset = self.inv.get_pin("vdd").ll().rotate_scale(-1,1)        
        vdd_x_offset = self.rbl_inv_offset.x + vdd_pin_offset.x - 0.5*drc["minwidth_metal2"]
        vdd_offset = vector(vdd_x_offset,source_offset.y)
        # route down a pitch so that it will drop a via to M2
        vdd_upper_offset = vdd_offset + vector(0,self.m2_pitch)
        self.add_wire(("metal1","via1","metal2"), [source_offset, vdd_offset, vdd_upper_offset])
        
        # DRAIN ROUTE
        # Route the drain to the RBL inverter input
        drain_offset = self.access_tx_offset + self.access_tx.active_contact_positions[0].rotate_scale(-1,1) \
                       + self.poly_contact_offset.rotate_scale(-1,1)
        mid1 = drain_offset - vector(0,2*self.m1_pitch)
        inv_A_offset = self.rbl_inv_offset + self.inv.get_pin("A").lc().rotate_scale(-1,1)
        mid2 = vector(inv_A_offset.x, mid1.y)
        self.add_path("metal1",[drain_offset, mid1, mid2, inv_A_offset])
        

    def route_vdd(self):
        # Add a rail in M1 from bottom to two along delay chain
        inv_gnd_offset = self.inv.get_pin("gnd").ll().rotate_scale(-1,1)
        # The rail is from the edge of the inverter bottom plus a metal spacing
        vdd_start = self.rbl_inv_offset.scale(1,0) + inv_gnd_offset.scale(1,0) + vector(self.m2_pitch,0)
        # It is the height of the entire RBL and bitcell
        self.add_layout_pin(text="vdd",
                            layer="metal2",
                            offset=vdd_start,
                            width=-drc["minwidth_metal2"],
                            height=self.rbl.height+self.bitcell.height+self.inv.width)

        # Connect the vdd pins directly to vdd
        vdd_pins = self.rbl.get_pin("vdd")
        for pin in vdd_pins:
            offset = vector(vdd_start.x,self.rbl_offset.y+pin.by()) - vector(drc["minwidth_metal2"],0)
            self.add_rect(layer="metal1",
                          offset=offset,
                          width=self.rbl_offset.x-vdd_start.x,
                          height=drc["minwidth_metal1"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=offset)

        # Add via for the delay chain
        inv_vdd_offset = self.inv.get_pin("vdd").ll().rotate_scale(-1,1)
        dc_offset = self.delay_chain_offset + inv_vdd_offset - vector(drc["minwidth_metal2"],self.m1m2_via.height)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=dc_offset)
        # Add via for the inverter
        inv_offset = self.rbl_inv_offset + inv_vdd_offset + vector(0,self.inv.width) - vector(drc["minwidth_metal2"],0)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=inv_offset)
        # Add a second pin that only goes about a quarter up. No need for full length.
        self.add_layout_pin(text="vdd",
                            layer="metal2",
                            offset=inv_offset.scale(1,0),
                            width=drc["minwidth_metal2"],
                            height=3.5*self.bitcell.height+self.inv.width)

        # Connect the vdd pins at 3.5 bitcells up.
        # Connecting in the middle of the bitcell means that there is likely
        # no M1M2 via for connecting the WL or gnd lines
        vdd_pins = self.get_pin("vdd")
        vdd_start = vector(vdd_pins[1].cx(),self.inv.width+3.5*self.bitcell.height)
        vdd_end = vector(vdd_pins[0].cx(),vdd_start.y)
        # Add a couple midpoints so that the wire will drop a via and then route horizontal on M1
        vdd_mid1 = vdd_start - vector(0,2*drc["metal2_to_metal2"])
        vdd_mid2 = vdd_end - vector(0,2*drc["metal2_to_metal2"])
        self.add_wire(("metal1","via1","metal2"), [vdd_start, vdd_mid1, vdd_mid2, vdd_end])

        
        
        
    def route_gnd(self):
        """ Route all signals connected to gnd """
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
            offset = vector(gnd_start.x,self.rbl_offset.y+pin.by())
            self.add_rect(layer="metal1",
                          offset=offset,
                          width=self.rbl_offset.x-gnd_start.x,
                          height=drc["minwidth_metal1"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=offset)

        # Add via for the delay chain
        offset = self.delay_chain_offset - vector(0.5*drc["metal1_to_metal1"],self.m1m2_via.height)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)

        # Add via for the inverter
        offset = self.rbl_inv_offset + vector(-0.5*drc["metal1_to_metal1"],self.inv.width)        
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=offset)

        # Connect the bitcell gnd pin to therail
        gnd_pins = self.get_pin("gnd")
        gnd_start = gnd_pins.uc()
        rbl_gnd_pins = self.rbl.get_pin("gnd")
        gnd_end = self.rbl_offset+rbl_gnd_pins.uc()
        # Add a couple midpoints so that the wire will drop a via and then route horizontal on M1
        gnd_mid1 = gnd_start + vector(0,2*drc["metal2_to_metal2"])
        gnd_mid2 = gnd_end + vector(0,2*drc["metal2_to_metal2"])
        self.add_wire(("metal1","via1","metal2"), [gnd_start, gnd_mid1, gnd_mid2, gnd_end])
        


        

