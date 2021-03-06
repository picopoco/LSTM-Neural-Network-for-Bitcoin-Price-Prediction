# coding=utf-8
import numpy as np
import pandas as pd
import h5py

# expected data columns in "filename_in.csv"
# time, open, high, low, close, accprice, volume

class ETL:
    """Extract Transform Load class for all data operations pre model inputs.
    Data is read in generative way to allow for large datafiles and low memory utilisation"""

    def __init__(self, filename_in, filename_out, batch_size, x_window_size, y_window_size, y_col, filter_cols, normalize):
        self._filename_in = filename_in
        self._filename_out = filename_out
        self._batch_size = batch_size
        self._x_window_size = x_window_size
        self._y_window_size = y_window_size
        self._y_col = y_col
        self._filter_cols = filter_cols
        self._normalize = normalize

    def clean_data(self):
        """Clean and Normalize the data in batches `batch_size` at a time"""
        data = pd.read_csv(self._filename_in, index_col=0)

        if self._filter_cols:
        # Remove any columns from data that we don't need by getting the difference between cols and filter list
            rm_cols = set(data.columns) - set(self._filter_cols)
            for col in rm_cols:
                del data[col]

        # Convert y-predict column name to numerical index
        y_col = list(data.columns).index(self._y_col)

        num_rows = len(data)
        x_data = []
        y_data = []
        i = 0
        while (i + self._x_window_size + self._y_window_size) <= num_rows:
            x_window_data = data[i:(i + self._x_window_size)]
            y_window_data = data[(i + self._x_window_size):(i + self._x_window_size + self._y_window_size)]

            # Remove(no use of) any windows that contain NaN
            if x_window_data.isnull().values.any() or y_window_data.isnull().values.any():
                i += 1
                continue

            if self._normalize:
                abs_base, x_window_data = self.zero_base_standardize(x_window_data)
                _, y_window_data = self.zero_base_standardize(y_window_data, abs_base=abs_base)

            # Average of the desired predicter y column
            # 평균 내는 이유는, y_window size가 1이 아닌경우에 대응하기 위함임.
            # 만약 y_window_size가 5면 x_window_size개 만큼을 이용해서
            # 그 이후 5개의 데이터 평균값을 예측하는 방식
            y_average = np.average(y_window_data.values[:, y_col])
            x_data.append(x_window_data.values)
            y_data.append(y_average)
            i += 1

            # Restrict yielding until we have enough in our batch. Then clear x, y data for next batch
            # 이 방식은 마지막(최신) 데이터 중 최대 batch size만큼은 yield하지 않아서
            # 사용하지 않게되는 문제가 있다.
            if i % self._batch_size == 0:
                # Convert from list to 3 dimensional numpy array [windows, window_val, val_dimension]
                x_np_arr = np.array(x_data)
                # y_np_arr.shape == (windows,)
                y_np_arr = np.array(y_data)
                x_data = []
                y_data = []
                yield (x_np_arr, y_np_arr)


    def create_clean_datafile(self):
        """Incrementally save a datafile of clean data ready for loading straight into model"""
        print('> Creating x & y data files...')

        # 이건 function call이 아니라 generator를 만든 것이다.
        data_gen = self.clean_data()

        i = 0
        with h5py.File(self._filename_out, 'w') as hf:
            x1, y1 = next(data_gen)
            # Initialize hdf5 x, y datasets with first chunk of data
            rcount_x = x1.shape[0]
            dset_x = hf.create_dataset('x', shape=x1.shape, maxshape=(None, x1.shape[1], x1.shape[2]), chunks=True)
            dset_x[:] = x1
            rcount_y = y1.shape[0]
            dset_y = hf.create_dataset('y', shape=y1.shape, maxshape=(None,), chunks=True)
            dset_y[:] = y1

            for x_batch, y_batch in data_gen:
                # Append batches to x, y hdf5 datasets
                print('\r> Creating x & y data files | Batch: {}'.format(i), end='')
                dset_x.resize(rcount_x + x_batch.shape[0], axis=0)
                dset_x[rcount_x:] = x_batch
                rcount_x += x_batch.shape[0]
                dset_y.resize(rcount_y + y_batch.shape[0], axis=0)
                dset_y[rcount_y:] = y_batch

                rcount_y += y_batch.shape[0]
                i += 1
        print('\n> Clean datasets created in file `' + self._filename_out + '`')

    def generate_clean_data(self, start_index=0):
        with h5py.File(self._filename_out, 'r') as hf:
            i = start_index
            while True:
                data_x = hf['x'][i:i + self._batch_size]
                data_y = hf['y'][i:i + self._batch_size]
                i += self._batch_size
                yield (data_x, data_y)

    def zero_base_standardize(self, data, abs_base=pd.DataFrame()):
        """Standardize dataframe to be zero based percentage returns from i=0"""
        if (abs_base.empty): abs_base = data.iloc[0]
        data_standardized = (data / abs_base) - 1
        return (abs_base, data_standardized)

    def min_max_normalize(self, data, data_min=pd.DataFrame(), data_max=pd.DataFrame()):
        """Normalize a Pandas dataframe using column-wise min-max normalization (can use custom min, max if desired)"""
        if (data_min.empty): data_min = data.min()
        if (data_max.empty): data_max = data.max()
        data_normalized = (data - data_min) / (data_max - data_min)
        return (data_min, data_max, data_normalized)