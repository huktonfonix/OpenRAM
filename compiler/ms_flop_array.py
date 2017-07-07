import debug
import design
from tech import drc
from math import log
from vector import vector
from globals import OPTS

class ms_flop_array(design.design):
    """
    An Array of D-Flipflops used for to store Data_in & Data_out of
    Write_driver & Sense_amp, address inputs of column_mux &
    hierdecoder
    """

    def __init__(self, name, columns, word_size):
        self.columns = columns
        self.word_size = word_size
        design.design.__init__(self, name)
        debug.info(1, "Creating %s" % self.name)

        c = reload(__import__(OPTS.config.ms_flop))
        self.mod_ms_flop = getattr(c, OPTS.config.ms_flop)

        self.create_layout()

    def create_layout(self):
        self.add_modules()
        self.setup_layout_constants()
        self.add_pins()
        self.create_ms_flop_array()
        self.add_labels()
        self.DRC_LVS()

    def add_modules(self):
        self.ms_flop = self.mod_ms_flop("ms_flop")
        self.add_mod(self.ms_flop)

    def setup_layout_constants(self):
        self.width = self.columns * self.ms_flop.width
        self.height = self.ms_flop.height
        self.words_per_row = self.columns / self.word_size


    def add_pins(self):
        for i in range(self.word_size):
            self.add_pin("din[{0}]".format(i))
        for i in range(self.word_size):
            self.add_pin("dout[{0}]".format(i))
            self.add_pin("dout_bar[{0}]".format(i))
        self.add_pin("clk")
        self.add_pin("vdd")
        self.add_pin("gnd")

    def create_ms_flop_array(self):
        for i in range(self.word_size):
            name = "Xdff%d" % i
            if (i % 2 == 0):
                x_off = i * self.ms_flop.width * self.words_per_row
                mirror = "None"
            else:
                if (self.words_per_row == 1):
                    x_off = (i + 1) * self.ms_flop.width
                    mirror="MY"
                else:
                    x_off = i * self.ms_flop.width * self.words_per_row
            self.add_inst(name=name,
                          mod=self.ms_flop,
                          offset=[x_off, 0], 
                          mirror=mirror)
            self.connect_inst(["din[{0}]".format(i),
                               "dout[{0}]".format(i),
                               "dout_bar[{0}]".format(i),
                               "clk",
                               "vdd", "gnd"])

    def add_labels(self):
        
        flop_pins = self.ms_flop.pins
        offsets = {}
        for i in range(self.word_size):
            i_str = "[{0}]".format(i)
            if (i % 2 == 0 or self.words_per_row > 1):
                base = vector(i * self.ms_flop.width * self.words_per_row, 0)
                offsets["gnd"+i_str] = base + flop_pins["gnd"].ll()
                offsets["din"+i_str] = base + flop_pins["din"].ll()
                offsets["dout"+i_str] = base + flop_pins["dout"].ll()
                offsets["dout_bar"+i_str] = base + flop_pins["dout_bar"].ll()
            else:
                base = vector((i + 1) * self.ms_flop.width, 0)
                offsets["gnd"+i_str] = base + flop_pins["gnd"].ll().scale(-1,1)
                offsets["din"+i_str] = base + flop_pins["din"].ll().scale(-1,1)
                offsets["dout"+i_str] = base + flop_pins["dout"].ll().scale(-1,1)
                offsets["dout_bar"+i_str] = base + flop_pins["dout_bar"].ll().scale(-1,1)


            for p in flop_pins.keys():
                if p=="vdd" or p=="clk": continue
                self.add_layout_pin(text=p+i_str,
                                    layer="metal2",
                                    offset=offsets[p+i_str],
                                    width=flop_pins[p].width(),
                                    height=flop_pins[p].height())

        # Continous "clk" rail along with label.
        self.add_layout_pin(text="clk",
                            layer="metal1",
                            offset=[0, flop_pins["clk"].ll()[1]],
                            width=self.width,
                            height=drc["minwidth_metal1"])

        # Continous "Vdd" rail along with label.
        self.add_layout_pin(text="vdd",
                            layer="metal1",
                            offset=[0, flop_pins["vdd"].center()[1] - 0.5 * drc["minwidth_metal1"]],
                            width=self.width,
                            height=drc["minwidth_metal1"])


    def delay(self, slew, load=0.0):
        result = self.ms_flop.delay(slew = slew, 
                                    load = load)
        return result
