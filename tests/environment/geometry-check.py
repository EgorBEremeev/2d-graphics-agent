from io import StringIO
import math

import ezdxf
from shapely.geometry import box

a, b = box(0, 0, 40, 30), box(20, 10, 60, 40)
union, intersection = a.union(b), a.intersection(b)
offset = a.buffer(2, join_style="mitre")
assert union.area == 2000 and intersection.area == 400
assert offset.bounds == (-2.0, -2.0, 42.0, 32.0)

doc = ezdxf.new("R2010")
doc.units = ezdxf.units.MM
doc.modelspace().add_lwpolyline(list(a.exterior.coords), close=True)
stream = StringIO()
doc.write(stream)
stream.seek(0)
read = ezdxf.read(stream)
points = list(read.modelspace().query("LWPOLYLINE")[0].get_points("xy"))
assert read.units == ezdxf.units.MM
assert math.isclose(max(x for x, y in points) - min(x for x, y in points), 40)
assert math.isclose(max(y for x, y in points) - min(y for x, y in points), 30)
print("union=2000 mm^2; intersection=400 mm^2; offset bounds=(-2,-2,42,32) mm")
print("DXF: units=mm, rectangle=40x30 mm, serialized and reopened in memory")