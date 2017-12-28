"""
Basic data handling for our Qcodes environment.
"""
import os
import numpy as np
from collections import OrderedDict
import h5py

from pysweep.data_storage import BaseStorage

class Data(BaseStorage):

    hdf5_raw_group = 'raw'

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.shapes = dict()

        if filepath is not None:
            self.export_spyview = True
            self.spyview_prefix = os.path.splitext(self.filepath)[0]
        else:
            self.export_spyview = False
            self.spyview_prefix = 'spyview'


    @staticmethod
    def get_column_names(page):
        colnames = [n for n in page.dtype.fields]
        return colnames


    @staticmethod
    def get_axes_names(page):
        n = Data.get_column_names(page)
        return n[:-1]


    @staticmethod
    def flatten_page(page, invert_axis_order=False):
        names = [n for n in page.dtype.fields]
        if invert_axis_order:
            names = names[:-1][::-1] + [names[-1]]

        shapes = [page.dtype[n].shape for n in names]
        dtypes = [page[n].dtype for n in names]
        sizes = [np.prod(s) for s in shapes]

        if ((1,) in shapes and len(set(shapes)) > 2) or ((1,) not in shapes and len(set(shapes)) > 1):
            raise NotImplementedError("Flattening of non-trivial shapes is currently not implemented.")

        blocksize = max(sizes)
        pagelen = page.size
        datasize = blocksize * pagelen
        data = np.zeros((datasize,), dtype=[(n,d) for n,d in zip(names, dtypes)])

        for name, size in zip(names, sizes):
            if size < blocksize:
                data[name] = np.vstack(blocksize*[page[name].reshape(-1)]).reshape(-1, order='F')
            else:
                data[name] = page[name].reshape(-1)

        return data


    @staticmethod
    def meta_info(data, exclude_dependent=True):
        ret = OrderedDict({})
        names = [n for n in data.dtype.fields]
        if exclude_dependent:
            names = names[:-1]

        for n in names:
            vals, nvals = np.unique(data[n], return_counts=True)
            ret[n] = {
                'values' : vals,
                'occurences' : nvals,
            }
        return ret


    def write_spyview_meta(self, fn, pagename):
        data = Data.flatten_page(self._pages[pagename], invert_axis_order=False)
        info = Data.meta_info(data)
        names = [n for n in data.dtype.fields]
        naxes = len(names[:-1])
        with open(fn, 'w') as f:
            for idx, n in enumerate(names[:-1]):
                m = info[n]
                f.write("{}\n{}\n{}\n{}\n".format(m['values'].size,
                                                  m['values'][0],
                                                  m['values'][-1],
                                                  n))
            for i in range(3 - naxes):
                f.write("{}\n{}\n{}\n{}\n".format(1,0,0,'None'))

            f.write("{}\n{}\n".format(idx+2, names[-1]))


    def write_spyview_data(self, fn, page):
        isnewfile = not os.path.exists(fn)

        data = Data.flatten_page(page, invert_axis_order=False)
        names = [n for n in data.dtype.fields]
        naxes = len(names[:-1])

        if names[-1] in self._pages:
            pagename = names[-1]
        elif names[-1].split(' [')[0] in self._pages:
            pagename = names[-1].split(' [')[0]
        else:
            raise ValueError("Cannot find page corresponding to this data.")

        alldata = Data.flatten_page(self._pages[pagename], invert_axis_order=False)
        col0_start = alldata[names[0]][0]

        metafn = os.path.splitext(fn)[0] + ".meta.txt"
        self.write_spyview_meta(metafn, pagename)

        with open(fn, 'a') as f:
            for i, row in enumerate(data):
                if row[names[0]] == col0_start:
                    f.write("\n")

                line = "\t".join(["{}".format(row[k]) for k in names])
                line += "\n"
                f.write(line)


    def add(self, record, write=True):
        super().add(record)
        if write and self.filepath is not None:
            self.write(record)


    def write(self, record=None):
        with h5py.File(self.filepath, 'a') as f:
            if record is None:
                pages = self._pages
            else:
                pages = self.record_to_pages(record)

            if self.hdf5_raw_group is not None:
                if self.hdf5_raw_group in f:
                    g = f[self.hdf5_raw_group]
                else:
                    g = f.create_group(self.hdf5_raw_group)
            else:
                g = f

            for name, arr in pages.items():
                if name in f:
                    d = g[name]
                else:
                    d = g.create_dataset(name, (0,), maxshape=(None,), dtype=arr.dtype, chunks=True)

                newlen = d.size + arr.size
                d.resize((newlen,))
                d[-arr.size:] = arr

                if self.export_spyview:
                    spyview_fn = self.spyview_prefix + "_{}.dat".format(name)
                    self.write_spyview_data(spyview_fn, arr)

class GridData(Data):

    grid_fit_mode = 'outer'
    grid_fill_val = np.nan

    def __init__(self, filepath):
        super().__init__(filepath)
        self.grids = {}

    def __getitem__(self, item):
        if item in self.grids:
            return self.get_griddata(item, mode=self.grid_fit_mode, fill=self.grid_fill_val),\
                self.grids[item]['coords']
        else:
            return super().__getitem__(item)

    @staticmethod
    def _coord_status(measured, full):
        _pts, _reps = np.unique(measured, return_counts=True)
        max_idx = np.where(_pts[-1] == full)[0][0]
        missing = np.max(_reps) - np.min(_reps)
        return dict(max_idx=max_idx, missing_for_rect=missing)

    def get_coord_status(self):
        coords = [(n, v['coords']) for n, v in self.grids.items()]
        info = {}
        for n, v in coords:
            tbl = GridData.flatten_page(self._pages[n])
            info[n] = [(cn, GridData._coord_status(tbl[cn], cv)) for cn, cv in v]
        return info

    def get_griddata(self, name, mode='outer', fill=np.nan):
        tbl = GridData.flatten_page(self._pages[name])
        info = [(cn, GridData._coord_status(tbl[cn], cv)) for cn, cv in self.grids[name]['coords']]

        if mode == 'outer':
            gridshape = tuple([v['max_idx']+1 for n, v in info])
            gridsize = np.prod(gridshape)

            if gridsize > tbl.size:
                grid = np.concatenate((tbl[name], np.ones(gridsize-tbl.size) * fill)).reshape(gridshape, order='F')
            elif gridsize == tbl.size:
                grid = tbl[name].reshape(gridshape, order='F')
            else:
                raise ValueError("Something unlikely happened: determined grid < data!?")

        else:
            raise ValueError("Invalid gridding-mode. Only 'outer' is supported at the moment.")

        return grid