import debug
import design
from tech import drc
from pinv import pinv
from contact import contact
from vector import vector
from globals import OPTS

class logic_effort_dc(design.design):
    """
    Generate a logic effort based delay chain.
    Input is a list contains the electrical effort of each stage.
    """

    def __init__(self, fanout_list, name="delay_chain"):
        """init function"""
        design.design.__init__(self, name)
        # FIXME: input should be logic effort value 
        # and there should be functions to get 
        # area efficient inverter stage list 

        # number of inverters including any fanout loads.
        self.fanout_list = fanout_list
        self.num_inverters = 1 + sum(fanout_list)
        self.num_top_half = round(self.num_inverters / 2.0)
        
        c = reload(__import__(OPTS.config.bitcell))
        self.mod_bitcell = getattr(c, OPTS.config.bitcell)
        self.bitcell = self.mod_bitcell()

        self.add_pins()
        self.create_module()
        self.route_inv()
        self.add_supply_rails()
        self.DRC_LVS()

    def add_pins(self):
        """ Add the pins of the delay chain"""
        self.add_pin("clk_in")
        self.add_pin("clk_out")
        self.add_pin("vdd")
        self.add_pin("gnd")

    def create_module(self):
        """ Add the inverter logical module """

        self.create_inv_list()

        self.inv = pinv(nmos_width=drc["minwidth_tx"])
        self.add_mod(self.inv)

        # We don't want the pinv output to connect to the adjacent stage,
        # so we space the inverters by M1 separation
        self.inv_spaced_width = self.inv.width + drc["metal1_to_metal1"]
        
        # half chain length is the width of the layout 
        # invs are stacked into 2 levels so input/output are close        
        self.width = self.num_top_half * self.inv_spaced_width
        self.height = 2 * self.inv.height

        self.add_inv_list()
        
    def create_inv_list(self):
        """ 
        Generate a list of inverters. Each inverter has a stage
        number and a flag indicating if it is a dummy load. This is 
        the order that they will get placed too.
        """
        # First stage is always 0 and is not a dummy load
        self.inv_list=[[0,False]]
        for stage_num,fanout_size in zip(range(len(self.fanout_list)),self.fanout_list):
            for i in range(fanout_size-1):
                # Add the dummy loads
                self.inv_list.append([stage_num+1, True])
                
            # Add the gate to drive the next stage
            self.inv_list.append([stage_num+1, False])

    def add_inv_list(self):
        """add the inverter and connect them based on the stage list """
        a_pin = self.inv.get_pin("A")
        dummy_load_counter = 1
        self.inv_inst_list = []
        for i in range(self.num_inverters):
            # First place the gates
            if i < self.num_top_half:
                # add top level that is upside down
                inv_offset = vector(i * self.inv_spaced_width, 2 * self.inv.height)
                inv_mirror="MX"
                via_offset = inv_offset + a_pin.ll().scale(1,-1)
                m1m2_via_rotate=270
            else:
                # add bottom level from right to left
                inv_offset = vector((self.num_inverters - i) * self.inv_spaced_width, 0)
                inv_mirror="MY"
                via_offset = inv_offset + a_pin.ll().scale(-1,1)
                m1m2_via_rotate=90

            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=via_offset,
                         rotate=m1m2_via_rotate)
            cur_inv=self.add_inst(name="dinv{}".format(i),
                                  mod=self.inv,
                                  offset=inv_offset,
                                  mirror=inv_mirror)
            # keep track of the inverter instances so we can use them to get the pins
            self.inv_inst_list.append(cur_inv)

            # Second connect them logically
            cur_stage = self.inv_list[i][0]
            next_stage = self.inv_list[i][0]+1
            if i == 0:
                input = "clk_in"
            else:
                input = "s{}".format(cur_stage)
            if i == self.num_inverters-1:
                output = "clk_out"
            else:                
                output = "s{}".format(next_stage)

            # if the gate is a dummy load don't connect the output
            # else reset the counter
            if self.inv_list[i][1]: 
                output = output+"n{0}".format(dummy_load_counter)
                dummy_load_counter += 1
            else:
                dummy_load_counter = 1
                    
            self.connect_inst(args=[input, output, "vdd", "gnd"])



    def route_inv(self):
        """add metal routing based on the stage list """
        start_inv = end_inv = 0
        z_pin = self.inv.get_pin("Z")
        a_pin = self.inv.get_pin("A")
        for fanout in self.fanout_list:
            # end inv number depends on the fan out number
            end_inv = start_inv + fanout
            start_inv_offset = self.inv_inst_list[start_inv].offset
            end_inv_offset = self.inv_inst_list[end_inv].offset
            if start_inv < self.num_top_half:
                start_o_offset =  start_inv_offset + z_pin.ll().scale(1,-1)
                m1m2_via_rotate = 270
                y_dir = -1
            else:
                start_o_offset = start_inv_offset + z_pin.ll().scale(-1,1)
                m1m2_via_rotate = 90
                y_dir = 1

            M2_start = start_o_offset + vector(0,drc["minwidth_metal2"]).scale(1,y_dir*0.5)
            
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=start_o_offset,
                         rotate=m1m2_via_rotate)

            if end_inv < self.num_top_half:
                end_i_offset =  end_inv_offset + a_pin.ll().scale(1,-1)
                M2_end = end_i_offset - vector(0, 0.5 * drc["minwidth_metal2"])
            else:
                end_i_offset =  end_inv_offset + a_pin.ll().scale(-1,1)
                M2_end = end_i_offset + vector(0, 0.5 * drc["minwidth_metal2"])

            # We need a wire if the routing spans multiple rows
            if start_inv < self.num_top_half and end_inv >= self.num_top_half:
                mid = vector(self.num_top_half * self.inv_spaced_width - 0.5 * drc["minwidth_metal2"],
                             M2_start[1])
                self.add_wire(("metal2", "via2", "metal3"),
                              [M2_start, mid, M2_end])
            else:
                self.add_path(("metal2"), [M2_start, M2_end])
            # set the start of next one after current end
            start_inv = end_inv

    def add_supply_rails(self):
        """ Add vdd and gnd rails """
        vdd_pin = self.inv.get_pin("vdd")
        gnd_pin = self.inv.get_pin("gnd")
        for i in range(3):
            (offset,y_dir)=self.get_gate_offset(0, self.inv.height, i)
            if i % 2:
                self.add_layout_pin(text="vdd",
                                    layer="metal1",
                                    offset=offset + vdd_pin.ll().scale(1,y_dir),
                                    width=self.width,
                                    height=drc["minwidth_metal1"])
            else:
                self.add_layout_pin(text="gnd",
                                    layer="metal1",
                                    offset=offset + gnd_pin.ll().scale(1,y_dir),
                                    width=self.width,
                                    height=drc["minwidth_metal1"])

