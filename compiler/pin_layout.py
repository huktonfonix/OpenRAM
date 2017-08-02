from vector import vector

class pin_layout:
    """
    A class to represent a rectangular design pin. It is limited to a
    single shape.
    """

    def __init__(self, name, rect, layer):
        self.name = name
        # repack the rect as a vector, just in case
        if type(rect[0])==vector:
            self.rect = rect
        else:
            self.rect = [vector(rect[0]),vector(rect[1])]
        self.layer = layer

    def __str__(self):
        """ override print function output """
        return "({} layer={} ll={} ur={})".format(self.name,self.layer,self.rect[0],self.rect[1])

    def __repr__(self):
        """ override print function output """
        return "({} layer={} ll={} ur={})".format(self.name,self.layer,self.rect[0],self.rect[1])
        
    def height(self):
        return self.rect[1].y-self.rect[0].y
    
    def width(self):
        return self.rect[1].x-self.rect[0].x

    def center(self):
        return vector(0.5*(self.rect[0].x+self.rect[1].x),0.5*(self.rect[0].y+self.rect[1].y))

    def cx(self):
        """ Center x """
        return 0.5*(self.rect[0].x+self.rect[1].x)

    def cy(self):
        """ Center y """
        return 0.5*(self.rect[0].y+self.rect[1].y)
    
    
    def ll(self):
        """ Lower left point """
        return self.rect[0]

    def lr(self):
        """ Lower right point """
        return vector(self.rect[1].x,self.rect[0].y)
    
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

    def ul(self):
        """ Upper left point """
        return vector(self.rect[0].x,self.rect[1].y)

    def rc(self):
        """ Right center point """
        return vector(self.rect[1].x,0.5*(self.rect[0].y+self.rect[1].y))

    def lc(self):
        """ Left center point """
        return vector(self.rect[0].x,0.5*(self.rect[0].y+self.rect[1].y))
    
    def rx(self):
        """ Right x value """
        return self.rect[1].x
