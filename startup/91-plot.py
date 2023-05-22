print(f"Loading {__file__}...")

import numpy as np
import matplotlib.pyplot as plt
from itertools import cycle
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.collections import PolyCollection
from bluesky.callbacks.core import CallbackBase

# grabbed this from bluesky v0.7.0 bluesky.callbacks.core
# because it no longer exists in later versions
def _get_obj_fields(fields):
    """
    If fields includes any objects, get their field names using obj.describe()

    ['det1', det_obj] -> ['det1, 'det_obj_field1, 'det_obj_field2']"
    """
    string_fields = []
    for field in fields:
        if isinstance(field, str):
            string_fields.append(field)
        else:
            try:
                field_list = sorted(field.describe().keys())
            except AttributeError:
                raise ValueError("Fields must be strings or objects with a "
                                 "'describe' method that return a dict.")
            string_fields.extend(field_list)
    return string_fields

class LivePlot3D(CallbackBase):
    """
    Build a function that updates a 3D plot from a stream of Events.

    Note: If your figure blocks the main thread when you are trying to
    scan with this callback, call `plt.ion()` in your IPython session.

    Parameters
    ----------
    y : str
        the name of a data field in an Event
    x : str, optional
        the name of a data field in an Event
        If None, use the Length of Y field
    z : str, optional
        the name of a data field in an Event
        If None, use the Event's sequence number.
    legend_keys : list, optional
        The list of keys to extract from the RunStart document and format
        in the legend of the plot. The legend will always show the
        scan_id followed by a colon ("1: ").  Each
    xlim : tuple, optional
        passed to Axes3D.set_xlim
    ylim : tuple, optional
        passed to Axes3D.set_ylim
    zlim : tuple, optional
        passed to Axes3D.set_zlim
    fig : Matplotlib Figure
    All additional keyword arguments are passed through to ``Axes.plot``.

    Examples
    --------
    >>> my_plotter = LivePlot3D('det', 'motor', legend_keys=['sample'])
    >>> RE(my_scan, my_plotter)
    """
    def __init__(self, y, x=None, z=None, *, legend_keys=None, xlim=None, ylim=None, zlim=None, fig=None, **kwargs):
        super().__init__()
        if fig is None:
            fig = plt.figure()
        self.fig = fig
        self.ax = fig.gca(projection='3d')

        if legend_keys is None:
            legend_keys = []
        self.legend_keys = ['scan_id']+legend_keys
        if x is not None:
            self.x, *others = _get_obj_fields([x])
        else:
            self.x = None

        if z is not None:
            self.z, *others = _get_obj_fields([z])
        else:
            self.z = None

        self.y, *others = _get_obj_fields([y])
        self.ax.set_ylabel(z or 'sequence #')
        self.ax.set_xlabel(x or 'point #')
        self.ax.set_zlabel(y)
        '''
        self.ax.set_ylabel(y)
        self.ax.set_xlabel(x or 'point #')
        self.ax.set_zlabel(z or 'sequence #')
        '''
        if xlim is not None:
            self.ax.set_xlim(*xlim)
        if ylim is not None:
            self.ax.set_zlim(*ylim)
        if zlim is not None:
            self.ax.set_ylim(*zlim)
        self.ax.margins(.1)
        self.kwargs = kwargs
        self.lines = []
        self.legend = None
        self.legend_title = " :: ".join([name for name in self.legend_keys])

    def start(self, doc):
        # The doc is not used; we just use the singal that a new run began.
        self.x_data, self.y_data, self.z_data = [], [], []
        self.label = " :: ".join(
            [str(doc.get(name, ' ')) for name in self.legend_keys])
        self.ax.plot([], [], [], label=self.label, **self.kwargs)
        self.legend = self.ax.legend(loc=0, title=self.legend_title).draggable()
        super().start(doc)

    def event(self, doc):
        "Unpack data from the event and call self.update()."
        try:
            new_y = doc['data'][self.y]

            if self.z is not None:
                new_z = doc['data'][self.z]
            else:
                new_z = doc['seq_num']

            if self.x is not None:
                new_x = doc['data'][self.x]
            else:
                new_x = list(range(len(new_y)))
        except KeyError:
            # wrong event stream, skip it
            return
        self.update_caches(new_x, new_y, new_z)
        self.update_plot()
        super().event(doc)

    def update_caches(self, x, y, z):
        self.x_data.append(x)
        self.y_data.append(y)
        self.z_data.append(z)

    def update_plot(self):
        self.ax.plot(self.x_data[-1],
                     np.ones_like(self.x_data[-1])*self.z_data[-1],
                     self.y_data[-1], label=self.label, **self.kwargs)


        N = self.z_data[-1]
        # Rescale and redraw.
        #self.ax.set_ylim3d(0, N)
        #self.ax.locator_params(axis='y', tight=None, nbins=N)
        self.ax.relim(visible_only=True)
        self.ax.autoscale_view(tight=True)
        self.ax.figure.canvas.draw_idle()

    def stop(self, doc):
        '''
        if not self.x_data:
            print('LivePlot did not get any data that corresponds to the '
                  'x axis. {}'.format(self.x))
        if not self.y_data:
            print('LivePlot did not get any data that corresponds to the '
                  'y axis. {}'.format(self.y))
        if len(self.y_data) != len(self.x_data):
            print('LivePlot has a different number of elements for x ({}) and'
                  'y ({})'.format(len(self.x_data), len(self.y_data)))
        '''
        super().stop(doc)

class LossyLivePlot3D(LivePlot3D):
     def __init__(self, N, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__cycle = cycle(range(N))
     def event(self, doc):
        if next(self.__cycle) == 0:
             super().event(doc)

