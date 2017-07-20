import debug
import design
import math
from tech import drc
from contact import contact
from pinv import pinv
from vector import vector
from globals import OPTS
from nand_2 import nand_2
from nand_3 import nand_3


class hierarchical_predecode(design.design):
    """
    Pre 2x4 and 3x8 decoder shared code.
    """
    def __init__(self, input_number):
        self.number_of_inputs = input_number
        self.number_of_outputs = int(math.pow(2, self.number_of_inputs))
        design.design.__init__(self, name="pre{0}x{1}".format(self.number_of_inputs,self.number_of_outputs))

        c = reload(__import__(OPTS.config.bitcell))
        self.mod_bitcell = getattr(c, OPTS.config.bitcell)
        self.bitcell_height = self.mod_bitcell.height

    
    def add_pins(self):
        for k in range(self.number_of_inputs):
            self.add_pin("A[{0}]".format(k))
        for i in range(self.number_of_outputs):
            self.add_pin("out[{0}]".format(i))
        self.add_pin("vdd")
        self.add_pin("gnd")

    def create_modules(self):
        """ Create the INV and NAND gate """
        
        self.inv = pinv()
        self.add_mod(self.inv)
        
        self.create_nand(self.number_of_inputs)
        self.add_mod(self.nand)

    def create_nand(self,inputs):
        """ Create the NAND for the predecode input stage """
        if inputs==2:
            self.nand = nand_2()
        elif inputs==3:
            self.nand = nand_3()
        else:
            debug.error("Invalid number of predecode inputs.",-1)
            
        
    # DEAD CODE?
    # def set_up_constrain(self):
    #     self.via_shift = (self.m1m2_via.second_layer_width - self.m1m2_via.first_layer_width) / 2
    #     self.metal2_extend_contact = (self.m1m2_via.second_layer_height - self.m1m2_via.contact_width) / 2
    #     self.via_shift = (self.m1m2_via.second_layer_width
    #                           - self.m1m2_via.first_layer_width) / 2
    #     self.metal2_extend_contact = (self.m1m2_via.second_layer_height 
    #                                       - self.m1m2_via.contact_width) / 2

    #     self.gap_between_rails = (self.metal2_extend_contact 
    #                              + drc["metal2_to_metal2"])
    #     self.gap_between_rail_offset = (self.gap_between_rails 
    #                                    + drc["minwidth_metal2"])

    def setup_constraints(self):
        layer_stack = ("metal1", "via1", "metal2")
        self.m1m2_via = contact(layer_stack=layer_stack) 
        #self.via_shift = (self.m1m2_via.second_layer_width - self.m1m2_via.first_layer_width) / 2
        #self.metal2_extend_contact = (self.m1m2_via.second_layer_height - self.m1m2_via.contact_width) / 2

        # Contact shift used connecting NAND3 inputs to the rail
        #self.contact_shift = (self.m1m2_via.first_layer_width - self.m1m2_via.contact_width) / 2

        self.metal2_space = drc["metal2_to_metal2"]
        self.metal2_pitch = self.m1m2_via.width + self.metal2_space

        # The rail offsets are indexed by the label
        self.rails = {}

        # Non inverted input rails
        for rail_index in range(self.number_of_inputs):
            xoffset = rail_index * self.metal2_pitch
            self.rails["in[{}]".format(rail_index)]=xoffset
        # x offset for input inverters
        self.x_off_inv_1 = self.number_of_inputs*self.metal2_pitch 
        
        # Creating the right hand side metal2 rails for output connections
        for rail_index in range(2 * self.number_of_inputs + 2):
            xoffset = self.x_off_inv_1 + self.inv.width + (rail_index * self.metal2_pitch)
            if rail_index == 0:
                self.rails["vdd"]=xoffset
            elif rail_index == 1:
                self.rails["gnd"]=xoffset
            elif rail_index < 2+self.number_of_inputs:
                self.rails["Abar[{}]".format(rail_index-2)]=xoffset
            else:
                self.rails["A[{}]".format(rail_index-self.number_of_inputs-2)]=xoffset

        # x offset to NAND decoder includes the left rails, mid rails and inverters
        self.x_off_nand = self.x_off_inv_1 + self.inv.width + (2 + 2*self.number_of_inputs) * self.metal2_pitch

                       
        # x offset to output inverters
        self.x_off_inv_2 = self.x_off_nand + self.nand.width

        # Height width are computed 
        self.width = self.x_off_inv_2 + self.inv.width
        self.height = self.number_of_outputs * self.nand.height
        
        # size = vector(self.width, self.height)
        # correct =vector(0, 0.5 * drc["minwidth_metal1"])
        # self.vdd_position = size - correct - vector(0, self.inv.height)
        # self.gnd_position = size - correct 

    def create_rails(self):
        """ Create all of the rails for the inputs and vdd/gnd/inputs_bar/inputs """
        for label in self.rails.keys():
            self.add_layout_pin(text=label,
                                layer="metal2",
                                offset=[self.rails[label], 0], 
                                width=drc["minwidth_metal2"],
                                height=self.height)

    def add_input_inverters(self):
        """ Create the input inverters to invert input signals for the decode stage. """
        for inv_num in range(self.number_of_inputs):
            name = "Xpre_inv[{0}]".format(inv_num)
            if (inv_num % 2 == 0):
                y_off = inv_num * (self.inv.height)
                offset = vector(self.x_off_inv_1, y_off)
                mirror = "R0"
            else:
                y_off = (inv_num + 1) * (self.inv.height)
                offset = vector(self.x_off_inv_1, y_off)
                mirror="MX"
            self.add_inst(name=name,
                          mod=self.inv,
                          offset=offset,
                          mirror=mirror)
            self.connect_inst(["A[{0}]".format(inv_num),
                               "Abar[{0}]".format(inv_num),
                               "vdd", "gnd"])
            
    def add_output_inverters(self):
        """ Create inverters for the inverted output decode signals. """
        
        self.decode_out_positions = []
        z_pin = self.inv.get_pin("Z")
        for inv_num in range(self.number_of_outputs):
            name = "Xpre2x4_nand_inv[{0}]".format(inv_num)
            if (inv_num % 2 == 0):
                y_factor = inv_num
                mirror = "R0"
            else:
                y_factor =inv_num + 1
                mirror = "MX"   
            base = vector(self.x_off_inv_2, self.inv.height * y_factor)   
            self.add_inst(name=name,
                          mod=self.inv,
                          offset=base,
                          mirror=mirror)
            self.connect_inst(["Z[{0}]".format(inv_num),
                               "out[{0}]".format(inv_num),
                               "vdd", "gnd"])

    def add_nand(self,connections):
        """ Create the NAND stage for the decodes """
        z_pin = self.nand.get_pin("Z")
        for nand_input in range(self.number_of_outputs):
            inout = str(self.number_of_inputs)+"x"+str(self.number_of_outputs)
            name = "Xpre{0}_nand[{1}]".format(inout,nand_input)
            if (nand_input % 2 == 0):
                y_off = nand_input * (self.nand.height)
                mirror = "R0"
                offset = vector(self.x_off_nand + self.nand.width,
                                y_off + z_pin.ly())
            else:
                y_off = (nand_input + 1) * (self.nand.height)
                mirror = "MX"
                offset =vector(self.x_off_nand + self.nand.width,
                               y_off - z_pin.ly() - drc["minwidth_metal1"])
            self.add_inst(name=name,
                          mod=self.nand,
                          offset=[self.x_off_nand, y_off],
                          mirror=mirror)
            self.add_rect(layer="metal1",
                          offset=offset,
                          width=drc["minwidth_metal1"],
                          height=drc["minwidth_metal1"])
            self.connect_inst(connections[nand_input])

    def route(self):
        self.route_input_inverters()
        self.route_nand_to_rails()
        #self.route_vdd_gnd_from_rails_to_gates()

    def route_input_inverters(self):
        """
        Route all conections of the inputs inverters [Inputs, outputs, vdd, gnd] 
        """
        for inv_num in range(self.number_of_inputs):
            (inv_offset, y_dir) = self.get_inverter_offset(self.x_off_inv_1, inv_num)
            
            out_pin = "Abar[{}]".format(inv_num)
            in_pin = "in[{}]".format(inv_num)
            
            #add output
            inv_out_offset = inv_offset+self.inv.get_pin("Z").ll().scale(1,y_dir)
            #- vector(0,drc["minwidth_metal1"]).scale(1,y_dir)
            self.add_rect(layer="metal1",
                          offset=inv_out_offset,
                          width=self.rails[out_pin]-inv_out_offset.x,
                          height=drc["minwidth_metal1"])
            self.add_via(layers = ("metal1", "via1", "metal2"),
                         offset=[self.rails[out_pin], inv_out_offset.y])
            
            #route input
            inv_in_offset = inv_offset+self.inv.get_pin("A").ll().scale(1,y_dir)
            self.add_rect(layer="metal1",
                          offset=[self.rails[in_pin], inv_in_offset.y],
                          width=inv_in_offset.x - self.rails[in_pin] + drc["minwidth_metal2"],
                          height=drc["minwidth_metal1"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=[self.rails[in_pin], inv_in_offset.y])

            # route vdd
            inv_vdd_offset = inv_offset+self.inv.get_pin("vdd").ll().scale(1,y_dir)
            self.add_rect(layer="metal1",
                          offset=inv_vdd_offset,
                          width=self.rails["vdd"] - inv_vdd_offset.x + drc["minwidth_metal2"],
                          height=drc["minwidth_metal1"])
            self.add_via(layers = ("metal1", "via1", "metal2"),
                         offset=[self.rails["vdd"], inv_vdd_offset.y])
            # route gnd
            inv_gnd_offset = inv_offset+self.inv.get_pin("gnd").ll().scale(1,y_dir)
            self.add_rect(layer="metal1",
                          offset=inv_gnd_offset,
                          width=self.rails["gnd"] - inv_gnd_offset.x + drc["minwidth_metal2"],
                          height=drc["minwidth_metal1"])
            self.add_via(layers = ("metal1", "via1", "metal2"),
                         offset=[self.rails["gnd"], inv_gnd_offset.y])

    def get_inverter_offset(self, x_offset, inv_num):
        """ Gets the base offset and y orientation of stacked rows of inverters.
        Input is which inverter in the stack from 0.."""

        if (inv_num % 2 == 0):
            base_offset=vector(x_offset, inv_num * self.inv.height)
            y_dir = 1
        else:
            base_offset=vector(x_offset, (inv_num+1) * self.inv.height - inv_num*drc["minwidth_metal1"])
            y_dir = -1
            
        return (base_offset,y_dir)

    def get_nand_offset(self, x_offset, nand_num):
        """ Gets the base offset and y orientation of stacked rows of inverters.
        Input is which inverter in the stack from 0.."""

        if (nand_num % 2 == 0):
            base_offset=vector(x_offset, nand_num * self.nand.height)
            y_dir = 1
        else:
            base_offset=vector(x_offset, (nand_num+1) * self.nand.height - nand_num*drc["minwidth_metal1"])
            y_dir = -1
            
        return (base_offset,y_dir)
    

    def route_nand_to_rails(self):
        # This 2D array defines the connection mapping 
        nand_input_line_combination = self.get_nand_input_line_combination()
        for k in range(self.number_of_outputs):
            # create x offset list         
            index_lst= nand_input_line_combination[k]
            (nand_offset,y_dir) = self.get_nand_offset(self.x_off_nand,k)

            if self.number_of_inputs == 2:
                gate_lst = ["A","B"]
            else:
                gate_lst = ["A","B","C"]                

            # this will connect pins A,B or A,B,C
            for rail_pin,gate_pin in zip(index_lst,gate_lst):
                pin_offset = nand_offset+self.nand.get_pin(gate_pin).ll().scale(1,y_dir)                
                self.add_rect(layer="metal1",
                              offset=[self.rails[rail_pin], pin_offset.y],
                              width=pin_offset.x - self.rails[rail_pin],
                              height=drc["minwidth_metal1"])
                self.add_via(layers=("metal1", "via1", "metal2"),
                             offset=[self.rails[rail_pin], pin_offset.y])



    def route_vdd_gnd_from_rails_to_gates(self):
        #via_correct = self.get_via_correct()
        via_correct = vector(0,0)
        for k in range(self.number_of_outputs):
            power_line_index = self.number_of_inputs + 1 - (k%2)
            yoffset = k * self.inv.height -  0.5 * drc["minwidth_metal1"]
            self.add_rect(layer="metal1",
                          offset=[self.rails_x_offset[power_line_index],
                                  yoffset],
                          width=self.x_off_nand - self.rails_x_offset[power_line_index],
                          height=drc["minwidth_metal1"])
            self.add_via(layers = ("metal1", "via1", "metal2"),
                         offset=[self.rails_x_offset[power_line_index] + self.gap_between_rails,
                                 yoffset - via_correct.y])

        yoffset = (self.number_of_outputs * self.inv.height 
                       - 0.5 * drc["minwidth_metal1"])
        index = self.number_of_inputs + 1
        self.add_rect(layer="metal1",
                      offset=[self.rails_x_offset[index], yoffset],
                      width=self.x_off_nand - self.rails_x_offset[index],
                      height=drc["minwidth_metal1"])
        self.add_via(layers = ("metal1", "via1", "metal2"),
                     offset=[self.rails_x_offset[index], yoffset] - via_correct)
