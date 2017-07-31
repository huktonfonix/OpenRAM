import debug
from tech import drc
import design
from vector import vector
from globals import OPTS

class tri_gate_array(design.design):
    """
    Dynamically generated tri gate array of all bitlines.  words_per_row
    """

    def __init__(self, columns, word_size):
        """Intial function of tri gate array """
        name = "tri_gate_array"
        design.design.__init__(self, name)
        debug.info(1, "Creating {0}".format(self.name))

        c = reload(__import__(OPTS.config.tri_gate))
        self.mod_tri_gate = getattr(c, OPTS.config.tri_gate)
        self.tri = self.mod_tri_gate("tri_gate")
        self.add_mod(self.tri)

        self.columns = columns
        self.word_size = word_size

        self.words_per_row = self.columns / self.word_size
        self.width = (self.columns / self.words_per_row) * self.tri.width
        self.height = self.tri.height
        
        self.create_layout()
        self.DRC_LVS()

    def create_layout(self):
        """generate layout """
        self.add_pins()
        self.create_array()
        self.add_metal_rails()
        self.add_layout_pins()

    def add_pins(self):
        """create the name of pins depend on the word size"""
        for i in range(self.word_size):
            self.add_pin("IN[{0}]".format(i))
        for i in range(self.word_size):
            self.add_pin("OUT[{0}]".format(i))
        for pin in ["en", "en_bar", "vdd", "gnd"]:
            self.add_pin(pin)

    def create_array(self):
        """add tri gate to the array """
        for i in range(0,self.columns,self.words_per_row):
            name = "Xtri_gate{0}".format(i)
            if (i % 2 == 0):
                x_off = i * self.tri.width
                mirror = "R0"
            else:
                if (self.words_per_row == 1):
                    x_off = (i + 1) * self.tri.width
                    mirror = "MY"
                else:
                    x_off = i * self.tri.width
                    mirror = "R0"
            self.add_inst(name=name,
                          mod=self.tri,
                          offset=[x_off, 0],
                          mirror = mirror)
            self.connect_inst(["in[{0}]".format(i),
                               "out[{0}]".format(i),
                               "en", "en_bar", "vdd", "gnd"])

    def add_metal_rails(self):
        """Connect en en_bar and vdd together """
        width = self.tri.width * self.columns - (self.words_per_row - 1) * self.tri.width
        en_pin = self.tri.get_pin("en")
        self.add_rect(layer="metal1",
                      offset=en_pin.ll().scale(0, 1),
                      width=width,
                      height=drc['minwidth_metal1'])
        enbar_pin = self.tri.get_pin("en_bar")
        self.add_rect(layer="metal1",
                      offset=enbar_pin.ll().scale(0, 1),
                      width=width,
                      height=drc['minwidth_metal1'])
        vdd_pin = self.tri.get_pin("vdd")
        self.add_rect(layer="metal1",
                      offset=vdd_pin.ll().scale(0, 1),
                      width=width,
                      height=drc['minwidth_metal1'])

    def add_layout_pins(self):
        gnd_pin = self.tri.get_pin("gnd")
        vdd_pin = self.tri.get_pin("vdd")
        in_pin = self.tri.get_pin("in")
        out_pin = self.tri.get_pin("out")
        en_pin = self.tri.get_pin("en")
        enbar_pin = self.tri.get_pin("en_bar")
        
        for i in range(0,self.columns,self.words_per_row):
            if (i % 2 == 0 or self.words_per_row > 1):
                base = vector(i*self.tri.width, 0)
                x_dir = 1
            else:
                base = vector((i+1)*self.tri.width, 0)
                x_dir = -1

            self.add_layout_pin(text="gnd",
                                layer="metal2",
                                offset=base + gnd_pin.ll().scale(x_dir,1),
                                width=x_dir*gnd_pin.width(),
                                height=gnd_pin.height())

            self.add_layout_pin(text="in[{0}]".format(i),
                                layer="metal2",
                                offset=base + in_pin.ll().scale(x_dir,1),
                                width=x_dir*in_pin.width(),
                                height=in_pin.height())

            self.add_layout_pin(text="out[{0}]".format(i),
                                layer="metal2",
                                offset=base + out_pin.ll().scale(x_dir,1),
                                width=x_dir*out_pin.width(),
                                height=out_pin.height())



        width = self.tri.width * self.columns - (self.words_per_row - 1) * self.tri.width
        self.add_layout_pin(layer="metal1",
                            offset=en_pin.ll().scale(0, 1),
                            width=width,
                            height=drc['minwidth_metal1'])
        
        self.add_rect(layer="metal1",
                      offset=enbar_pin.ll().scale(0, 1),
                      width=width,
                      height=drc['minwidth_metal1'])
        
        self.add_rect(layer="metal1",
                      offset=vdd_pin.ll().scale(0, 1),
                      width=width,
                      height=drc['minwidth_metal1'])
            


    def delay(self, slew, load=0.0):
        result = self.tri.delay(slew = slew, load = load)
        return result
