import debug
import design
from tech import drc, spice
from vector import vector
from globals import OPTS



class bitcell_array(design.design):
    """
    Creates a rows x cols array of memory cells. Assumes bit-lines
    and word line is connected by abutment.
    Connects the word lines and bit lines.
    """

    def __init__(self, name, cols, rows):
        design.design.__init__(self, name)
        debug.info(1, "Creating {0} {1} x {2}".format(self.name, rows, cols))


        self.column_size = cols
        self.row_size = rows

        c = reload(__import__(OPTS.config.bitcell))
        self.mod_bitcell = getattr(c, OPTS.config.bitcell)

        self.add_pins()
        self.create_layout()
        self.add_labels()
        self.DRC_LVS()

    def add_pins(self):
        for col in range(self.column_size):
            self.add_pin("bl[{0}]".format(col))
            self.add_pin("br[{0}]".format(col))
        for row in range(self.row_size):
            self.add_pin("wl[{0}]".format(row))
        self.add_pin("vdd")
        self.add_pin("gnd")

    def create_layout(self):
        self.create_cell()
        self.setup_layout_constants()
        self.add_cells()
        self.offset_all_coordinates()

    def setup_layout_constants(self):
        self.vdd_positions = []
        self.gnd_positions = []
        self.BL_positions = []
        self.BR_positions = []
        self.WL_positions = []
        self.height = self.row_size * self.cell.height
        self.width = self.column_size * self.cell.width

    def create_cell(self):
        self.cell = self.mod_bitcell()
        self.add_mod(self.cell)

    def add_cells(self):
        xoffset = 0.0
        for col in range(self.column_size):
            yoffset = 0.0
            for row in range(self.row_size):
                name = "bit_r{0}_c{1}".format(row, col)

                if row % 2:
                    tempy = yoffset + self.cell.height
                    dir_key = "MX"
                else:
                    tempy = yoffset
                    dir_key = "R0"

                self.add_inst(name=name,
                              mod=self.cell,
                              offset=[xoffset, tempy],
                              mirror=dir_key)
                self.connect_inst(["bl[{0}]".format(col),
                                   "br[{0}]".format(col),
                                   "wl[{0}]".format(row),
                                   "vdd",
                                   "gnd"])
                yoffset += self.cell.height
            xoffset += self.cell.width

    def add_labels(self):
        bitcell_pins = self.cell.pins
        offset = vector(0.0, 0.0)
        for col in range(self.column_size):
            self.add_layout_pin(text="bl[{0}]".format(col),
                                layer="metal2",
                                offset=offset + vector(bitcell_pins["BL"].ll()[0],0),
                                width=bitcell_pins["BL"].width(),
                                height=self.cell.height*self.row_size)
            self.add_layout_pin(text="br[{0}]".format(col),
                                layer="metal2",
                                offset=offset + vector(bitcell_pins["BR"].ll()[0],0),
                                width=bitcell_pins["BL"].width(),
                                height=self.cell.height*self.row_size)

            # gnd offset is 0 in our cell, but it be non-zero
            self.add_layout_pin(text="gnd", 
                                layer="metal2",
                                offset=offset + bitcell_pins["gnd"].ll(),
                                width=bitcell_pins["gnd"].width(),
                                height=self.cell.height*self.row_size)
            self.gnd_positions.append(offset + vector(bitcell_pins["gnd"].ll()[0],0))
            # increments to the next column width
            offset.x += self.cell.width

        offset.x = 0.0
        for row in range(self.row_size):
            # flipped row
            if row % 2:
                base_offset = offset + vector(0, self.cell.height)
                vdd_offset = base_offset - vector(0,bitcell_pins["vdd"].ur()[1])
                wl_offset =  base_offset - vector(0,bitcell_pins["WL"].ur()[1])
            # unflipped row
            else:
                vdd_offset = offset + vector(0,bitcell_pins["vdd"].ll()[1])
                wl_offset = offset + vector(0,bitcell_pins["WL"].ll()[1])
            # add vdd label and offset
            self.add_layout_pin(text="vdd",
                                layer="metal1",
                                offset=vdd_offset,
                                width=self.cell.width*self.column_size,
                                height=drc["minwidth_metal1"])
            self.vdd_positions.append(vdd_offset)
            # add wl label and offset
            self.add_layout_pin(text="wl[{0}]".format(row),
                                layer="metal1",
                                offset=wl_offset,
                                width=self.cell.width*self.column_size,
                                height=drc["minwidth_metal1"])

            # increments to the next row height
            offset.y += self.cell.height

    def delay(self, slew, load=0):
        from tech import drc
        wl_wire = self.gen_wl_wire()
        wl_wire.return_delay_over_wire(slew)

        wl_to_cell_delay = wl_wire.return_delay_over_wire(slew)
        # hypothetical delay from cell to bl end without sense amp
        bl_wire = self.gen_bl_wire()
        cell_load = 2 * bl_wire.return_input_cap() # we ingore the wire r
                                                   # hence just use the whole c
        bl_swing = 0.1
        cell_delay = self.cell.delay(wl_to_cell_delay.slew, cell_load, swing = bl_swing)

        #we do not consider the delay over the wire for now
        return self.return_delay(cell_delay.delay+wl_to_cell_delay.delay,
                                 wl_to_cell_delay.slew)

    def gen_wl_wire(self):
        wl_wire = self.generate_rc_net(int(self.column_size), self.width, drc["minwidth_metal1"])
        wl_wire.wire_c = 2*spice["min_tx_gate_c"] + wl_wire.wire_c # 2 access tx gate per cell
        return wl_wire

    def gen_bl_wire(self):
        bl_pos = 0
        bl_wire = self.generate_rc_net(int(self.row_size-bl_pos), self.height, drc["minwidth_metal1"])
        bl_wire.wire_c =spice["min_tx_drain_c"] + bl_wire.wire_c # 1 access tx d/s per cell
        return bl_wire

    def output_load(self, bl_pos=0):
        bl_wire = self.gen_bl_wire()
        return bl_wire.wire_c # sense amp only need to charge small portion of the bl
                              # set as one segment for now

    def input_load(self):
        wl_wire = self.gen_wl_wire()
        return wl_wire.return_input_cap()
