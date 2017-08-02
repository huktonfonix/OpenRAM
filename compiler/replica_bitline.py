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
        #self.route()
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
                      rotate=90)
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
        a_pin = self.inv.get_pin("A")
        z_pin = self.inv.get_pin("Z")
        # calculate pin offset
        out_offset = self.rbl_inv_offset + z_pin.ll()
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=out_offset)

        rbl_inv_in = self.rbl_inv_offset + a_pin.ll()
        rbl_offset = self.replica_bitline_offset + self.bitcell.get_pin("BL").ll().scale(1,0)
        clk_out_pin = self.delay_chain.get_pin("out")
        delay_chain_output = self.delay_chain_offset + clk_out_pin.ll().rotate_scale(-1,1)
        vdd_offset = vector(self.delay_chain_offset.x + 9 * drc["minwidth_metal2"], 
                            self.height)
        self.create_input()

        self.route_rbl_t_rbl_inv(rbl_offset, rbl_inv_in)
        self.route_access_tx(delay_chain_output, rbl_inv_in, vdd_offset)
        self.route_vdd()
        self.route_gnd()
        # route loads after gnd and vdd created
        self.route_loads(vdd_offset)
        self.route_replica_cell(vdd_offset)

    def create_input(self):
        # create routing module based on module offset
        clk_in_pin = self.delay_chain.get_pin("in")
        input_offset = self.delay_chain_offset + clk_in_pin.ll().rotate_scale(-1,1)
        mid1 = [input_offset.x, self.en_input_offset.y]
        self.add_path("metal1", [self.en_input_offset, mid1, input_offset])

        self.add_label(text="en",
                       layer="metal1",
                       offset=self.en_input_offset)

    def route_rbl_t_rbl_inv(self, rbl_offset, rbl_inv_in):
        # rbl_inv input to M3
        mid1 = rbl_inv_in - vector(0,  
                                  drc["metal2_to_metal2"] + self.m1m2_via.width)
        mid2 = vector(self.en_nor_offset.x + 3 * drc["metal1_to_metal1"],
                      mid1.y)
        mid3 = vector(mid2.x,
                      self.replica_bitline_offset.y - self.replica_bitcell.height
                          - 0.5 * (self.m1m2_via.height + drc["metal1_to_metal1"])
                          - 2 * drc["metal1_to_metal1"])
        self.add_wire(layers=("metal2", "via1", "metal1"),
                      coordinates=[rbl_inv_in, mid1, mid2, mid3])

        # need to fix the mid point as this is done with two wire
        # this seems to cover the metal1 error of the wire
        offset = mid3 - vector( [0.5 * drc["minwidth_metal1"]] * 2)
        self.add_rect(layer="metal1",
                      offset=offset,
                      width=drc["minwidth_metal1"],
                      height=drc["minwidth_metal1"])

        mid4 = [rbl_offset.x, mid3.y]
        self.add_wire(layers=("metal1", "via1", "metal2"),
                      coordinates=[rbl_offset, mid4, mid3])

    def route_access_tx(self, delay_chain_output, rbl_inv_in, vdd_offset):
        self.route_tx_gate(delay_chain_output)
        self.route_tx_drain(vdd_offset)
        self.route_tx_source(rbl_inv_in)

    def route_tx_gate(self, delay_chain_output):
        # gate input for access tx
        offset = (self.access_tx.poly_positions[0].rotate_scale(0,1)
                      + self.access_tx_offset)
        width = -6 * drc["minwidth_metal1"]
        self.add_rect(layer="poly",
                      offset=offset,
                      width=width,
                      height=drc["minwidth_poly"])
        y_off = 0.5 * (drc["minwidth_poly"] - self.poly_contact.height)
        offset = offset + vector(width, y_off)
        self.add_contact(layers=("poly", "contact", "metal1"),
                         offset=offset)
        # route gate to delay_chain output
        gate_offset = offset + vector(0.5 * drc["minwidth_metal1"],
                                      0.5 * self.poly_contact.width)
        self.route_access_tx_t_delay_chain(gate_offset, delay_chain_output)
        self.route_access_tx_t_WL(gate_offset)

    def route_access_tx_t_delay_chain(self, offset, delay_chain_output):
        m2rail_space = (drc["minwidth_metal2"] + drc["metal2_to_metal2"]) 
        mid1 = vector(offset.x, self.delay_chain_offset.y - 3 * m2rail_space)
        mid2 = [delay_chain_output.x, mid1.y]
        # Note the inverted wire stack
        self.add_wire(layers=("metal1", "via1", "metal2"),
                      coordinates=[offset, mid1, mid2, delay_chain_output])
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=delay_chain_output,
                     mirror="MX")

    def route_access_tx_t_WL(self, offset):
        m1m2_via_offset = offset - vector(0.5 * self.m1m2_via.width,
                                          0.5 * self.m1m2_via.height)
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=m1m2_via_offset)
        # route gate to RC WL
        RC_WL = self.replica_bitline_offset - self.bitcell.get_pin("WL").ll().scale(0,1)
        mid1 = vector(offset.x, 0)
        mid2 = vector(self.en_nor_offset.x + 3 * drc["metal1_to_metal1"], mid1.y)
        mid3 = vector(RC_WL.x - drc["minwidth_metal1"] - self.m1m2_via.height, mid1.y)
        mid4 = vector(mid3.x, RC_WL.y)
        self.add_path("metal2", [offset, mid1, mid2, mid3, mid4])

        offset = mid4 - vector([0.5 * drc["minwidth_metal1"]] * 2)
        width = RC_WL.x - offset.x
        # enter the bit line array with metal1
        via_offset = [mid4.x - 0.5 * self.m1m2_via.width,
                      offset.y 
                          - 0.5 * (self.m1m2_via.height 
                                             - drc["minwidth_metal1"])]
        self.add_via(layers=("metal1", "via1", "metal2"),
                     offset=via_offset)
        self.add_rect(layer="metal1",
                      offset=offset,
                      width=width,
                      height=drc["minwidth_metal1"])

    def route_tx_drain(self,vdd_offset):
        # route drain to Vdd
        active_offset = self.access_tx.active_contact_positions[1].rotate_scale(-1,1)
        correct = vector(-0.5 * drc["minwidth_metal1"], 
                         0.5 * self.access_tx.active_contact.width)
        drain_offset = self.access_tx_offset + active_offset + correct
        close_Vdd_offset = self.rbl_inv_offset + vector(0, self.inv.height)
        self.add_path("metal1", [drain_offset, close_Vdd_offset])

        mid = [vdd_offset.x, close_Vdd_offset.y]
        self.add_wire(layers=("metal1", "via1", "metal2"),
                      coordinates=[close_Vdd_offset, mid, vdd_offset])

    def route_tx_source(self, rbl_inv_in):
        # route source to BL inv input which is connected to BL
        active_offset = self.access_tx.active_contact_positions[0].rotate_scale(-1,1)
        correct = vector(-0.5 * drc["minwidth_metal1"], 
                         0.5 * self.access_tx.active_contact.width)
        source_offset = self.access_tx_offset + active_offset + correct
        self.add_path("metal1", [source_offset, rbl_inv_in])

    def route_vdd(self):
        """ Route the vdd connections together and add a layout pin """
        vdd_offset = vector(0, self.height)
        self.add_layout_pin(text="vdd",
                            layer="metal1",
                            offset=vdd_offset,
                            width=self.width,
                            height=drc["minwidth_metal1"])
        # delay chain vdd to vertical vdd  rail and
        start = self.delay_chain_offset - vector(0.5 * self.delay_chain.height, 0)
        m1rail_space = (drc["minwidth_metal1"] + drc["metal1_to_metal1"])
        mid1 = start - vector(0, m1rail_space)
        mid2 = vector(self.delay_chain_offset.x + 9 * drc["minwidth_metal2"],
                      mid1.y)
        end = [mid2.x, vdd_offset.y]
        self.add_path(layer=("metal1"), 
                      coordinates=[start, mid1, mid2])
        self.add_wire(layers=("metal1", "via1", "metal2"), 
                      coordinates=[mid1, mid2, end])

        # add layout pin
        
    def route_gnd(self):
        """ Route the ground connections together and add a layout pin """
        # route delay chain gnd to rbl_inv gnd
        # gnd Node between rbl_inv access tx and delay chain, and is below
        # en_input
        self.gnd_position = self.delay_chain_offset
        
        rbl_gnd_offset = self.rbl_inv_offset 
        mid1 = vector(0, self.rbl_inv_offset.y)
        rail2_space = drc["minwidth_metal2"] + drc["metal2_to_metal2"]
        y_off = self.gnd_position.y + self.delay_chain.width + rail2_space
        mid2 = vector(mid1.x, y_off)
        share_gnd = vector(self.gnd_position.x, mid2.y)
        # Note the inverted stacks
        lst = [rbl_gnd_offset, mid1, mid2, share_gnd, self.gnd_position]
        self.add_wire(layers=("metal1", "via1", "metal2"),
                      coordinates=lst)
        self.add_label(text="gnd",
                       layer="metal1",
                       offset=self.gnd_position)
        # connect to the metal1 gnd of delay chain
        offset = mid2 - vector(0.5 * drc["minwidth_metal1"], 0)
        self.add_rect(layer="metal1",
                      offset=offset,
                      width=drc["minwidth_metal1"],
                      height=-self.delay_chain.width)
        offset = [offset.x + self.delay_chain.height,
                  mid2.y]
        self.add_rect(layer="metal1",
                      offset=offset,
                      width=drc["minwidth_metal1"],
                      height=-self.delay_chain.width)

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
