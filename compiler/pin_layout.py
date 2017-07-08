from vector import vector

class pin_layout:
    """
    A class to represent a rectangular design pin. It is limited to a
    single shape.
    """

    def __init__(self, name, rect, layer):
        self.name = name
        self.rect = rect
        self.layer = layer

    def height(self):
        return self.rect[1].y-self.rect[0].y
    
    def width(self):
        return self.rect[1].x-self.rect[0].x

    def center(self):
        return vector(0.5*(self.rect[0].x+self.rect[1].x),0.5*(self.rect[0].y+self.rect[1].y))

    def ll(self):
        """ Lower left point """
        return self.rect[0]

    def ly(self):
        """ Lower y value """
        return self.rect[0].y

    def lx(self):
        """ Left x value """
        return self.rect[0].x
    
    def ur(self):
        """ Upper right point """
        return self.rect[1]
    
    def uy(self):
        """ Upper y value """
        return self.rect[1].y

    def rx(self):
        """ Right x value """
        return self.rect[1].x
