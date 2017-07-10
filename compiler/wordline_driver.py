from tech import drc, parameter
import debug
import design
from math import log
from math import sqrt
import math
from pinv import pinv
from nand_2 import nand_2
from vector import vector
from globals import OPTS

class wordline_driver(design.design):
    """
    Creates a Wordline Driver
    Generates the wordline-driver to drive the bitcell
    """

    def __init__(self, name, rows):
        design.design.__init__(self, name)

        self.rows = rows
        self.add_pins()
        self.design_layout()
        self.DRC_LVS()

    def add_pins(self):
        # inputs to wordline_driver.
        for i in range(self.rows):
            self.add_pin("decode[{0}]".format(i))
        # Outputs from wordline_driver.
        for i in range(self.rows):
            self.add_pin("wl[{0}]".format(i))
        self.add_pin("clk")
        self.add_pin("vdd")
        self.add_pin("gnd")

    def design_layout(self):
        self.add_layout()
        self.offsets_of_gates()
        self.create_layout()

    def add_layout(self):
        self.inv = pinv(nmos_width=drc["minwidth_tx"],
                        beta=parameter["pinv_beta"])
        self.add_mod(self.inv)

        self.NAND2 = nand_2(nmos_width=2*drc["minwidth_tx"])
        self.add_mod(self.NAND2)




    def offsets_of_gates(self):
        self.x_offset0 = 2 * drc["minwidth_metal1"] + 5 * drc["metal1_to_metal1"]
        self.x_offset1 = self.x_offset0 + self.inv.width
        self.x_offset2 = self.x_offset1 + self.NAND2.width

        self.width = self.x_offset2 + self.inv.width
        self.height = self.inv.height * self.rows

    def create_layout(self):
        # Clk connection
        self.add_layout_pin(text="clk",
                            layer="metal2",
                            offset=[drc["minwidth_metal1"] + 2 * drc["metal1_to_metal1"],
                                    2 * drc["minwidth_metal1"]],
                            width=drc["minwidth_metal2"],
                            height=self.height + 4*drc["minwidth_metal1"])
        
        self.add_layout_pin(text="gnd[0]",
                            layer="metal1",
                            offset=[0, -0.5*drc["minwidth_metal1"]],
                            width=self.x_offset0,
                            height=drc["minwidth_metal1"])
        
        for row in range(self.rows):
            name_inv1 = "Wordline_driver_inv_clk{}".format(row)
            name_nand = "Wordline_driver_nand{}".format(row)
            name_inv2 = "Wordline_driver_inv{}".format(row)

            inv_nand2B_connection_height = (abs(self.inv.get_pin("Z").ll().y 
                                                - self.NAND2.get_pin("B").ll().y)
                                            + drc["minwidth_metal1"])

            if (row % 2):
                y_offset = self.inv.height*(row + 1)
                inst_mirror = "MX"
                cell_dir = vector(0,-1)
                m1tm2_rotate=270
                m1tm2_mirror="R0"
            else:
                y_offset = self.inv.height*row
                inst_mirror = "R0"
                cell_dir = vector(0,1)
                m1tm2_rotate=90
                m1tm2_mirror="MX"

            name_inv1_offset = [self.x_offset0, y_offset]
            nand2_offset=[self.x_offset1, y_offset]
            inv2_offset=[self.x_offset2, y_offset]
            base_offset = vector(self.width, y_offset)

            # Extend vdd and gnd of wordline_driver
            yoffset = (row + 1) * self.inv.height - 0.5 * drc["minwidth_metal1"]
            if (row % 2):
                pin_name = "gnd[{0}]".format((row+1)/2)
            else:
                pin_name = "vdd[{0}]".format((row+1)/2)
                
            self.add_layout_pin(text=pin_name,
                                layer="metal1",
                                offset=[0, yoffset],
                                width=self.x_offset0,
                                height=drc["minwidth_metal1"])
            
            
            # add inv1 based on the info above
            self.add_inst(name=name_inv1,
                          mod=self.inv,
                          offset=name_inv1_offset,
                          mirror=inst_mirror )
            self.connect_inst(["clk", "clk_bar[{0}]".format(row),
                               "vdd", "gnd"])
            # add nand 2
            self.add_inst(name=name_nand,
                          mod=self.NAND2,
                          offset=nand2_offset,
                          mirror=inst_mirror)
            self.connect_inst(["decode[{0}]".format(row),
                               "clk_bar[{0}]".format(row),
                               "net[{0}]".format(row),
                               "vdd", "gnd"])
            # add inv2
            self.add_inst(name=name_inv2,
                          mod=self.inv,
                          offset=inv2_offset,
                          mirror=inst_mirror)
            self.connect_inst(["net[{0}]".format(row),
                               "wl[{0}]".format(row),
                               "vdd", "gnd"])

            # clk connection
            clk_offset= vector(drc["minwidth_metal1"] + 2 * drc["metal1_to_metal1"],
                               y_offset + cell_dir.y * self.inv.get_pin("A").ly())
            self.add_rect(layer="metal1",
                          offset=clk_offset,
                          width=self.x_offset0 - 2*drc["metal1_to_metal1"],
                          height=cell_dir.y *drc["minwidth_metal1"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                         offset=clk_offset)

            # first inv to nand2 B
            inv_to_nand2B_offset = [self.x_offset1 - drc["minwidth_metal1"],
                                  y_offset + cell_dir.y * self.NAND2.get_pin("B").ly()]
            self.add_rect(layer="metal1",
                          offset=inv_to_nand2B_offset,
                          width=drc["minwidth_metal1"],
                          height=cell_dir.y*inv_nand2B_connection_height)
            # Nand2 out to 2nd inv
            nand2_to_2ndinv_offset =[self.x_offset2,
                                  y_offset + cell_dir.y * self.NAND2.get_pin("Z").ly()]
            self.add_rect(layer="metal1",
                          offset=nand2_to_2ndinv_offset,
                          width=drc["minwidth_metal1"],
                          height=cell_dir.y * drc["minwidth_metal1"])

            # connect the decoder input pin to nand2 A
            input_via_offset=vector(0, y_offset + cell_dir.y*self.NAND2.get_pin("A").ly())
            mid_via_offset = vector(clk_offset.x,input_via_offset.y) + vector(drc["minwidth_metal2"]+drc["metal2_to_metal2"],0) 
            # must go over the clk line in M2
            self.add_via(layers=("metal1", "via1", "metal2"),
                          offset=input_via_offset,
                          mirror=inst_mirror)
            self.add_layout_pin(text="decode[{0}]".format(row),
                                layer="metal1",
                                offset=input_via_offset,
                                width=mid_via_offset.x,
                                height=cell_dir.y*drc["minwidth_metal1"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                          offset=mid_via_offset,
                          mirror=inst_mirror)
            # now connect to the nand2 A
            self.add_rect(layer="metal2",
                          offset=mid_via_offset,
                          width=self.x_offset1-mid_via_offset.x,
                          height=cell_dir.y*drc["minwidth_metal2"])
            self.add_via(layers=("metal1", "via1", "metal2"),
                          offset=[self.x_offset1,
                                  y_offset + cell_dir.y * self.NAND2.get_pin("A").ly()],
                          rotate=m1tm2_rotate,
                          mirror=m1tm2_mirror)

            # output each WL on the right
            wl_offset = base_offset + self.inv.get_pin("Z").ll().scale(cell_dir)
            self.add_layout_pin(text="wl[{0}]".format(row),
                                layer="metal1",
                                offset=wl_offset,
                                width=drc["minwidth_metal1"]*cell_dir.y,
                                height=drc["minwidth_metal1"]*cell_dir.y)


    def delay(self, slew, load=0):
        # decode -> net
        decode_t_net = self.NAND2.delay(slew, self.inv.input_load())

        # net -> wl
        net_t_wl = self.inv.delay(decode_t_net.slew, load)

        result = decode_t_net + net_t_wl
        return result
    
    def input_load(self):
        return self.NAND2.input_load()
