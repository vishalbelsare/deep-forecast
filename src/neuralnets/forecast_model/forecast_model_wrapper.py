import __builtin__
from collections import OrderedDict

import numpy as np
import pandas as pd
from keras import backend as K
from keras.wrappers.scikit_learn import BaseWrapper
from scoop.futures import map
from sklearn.model_selection import PredefinedSplit, TimeSeriesSplit

from src.neuralnets.forecast_model.forecast_models import ForecastModel
from src.utils import data_utils
from preprocessing import DifferenceTransformer
from scipy.ndimage import shift


def clear_session(dumy):
    K.clear_session()


class ForecastRegressor(BaseWrapper):
    def __init__(self, build_fn, data_params=None, params=None, difference=False):
        self.data_params = None
        self.x_vars = None
        self.x_lags = None
        self.y_vars = None
        self.y_lags = None
        self.difference = difference

        self.is_data_set = False
        self.is_fitted = False
        self.is_multioutput = None

        self.x = None
        self.y = None
        self.x_train = None
        self.x_val = None
        self.x_test = None
        self.y_train = None
        self.y_val = None
        self.y_test = None

        self.transformer = DifferenceTransformer()

        if data_params is not None:
            self.set_data_params(**data_params)

        super(ForecastRegressor, self).__init__(build_fn, **params)

    def set_data_params(self, **data_params):
        # set internal variables
        self.data_params = data_params

        self.x_vars = data_params['vars'][0]
        self.y_vars = data_params['vars'][1]
        self.x_lags = data_params['x_lags']
        self.y_lags = data_params['y_lags']

        self.is_multioutput = self.y_vars > 1
        self.is_data_set = True
        self.is_fitted = False

        # get xy lagged data
        self.x, self.y = data_utils.get_data_in_shape(**data_params)

        # difference data
        if self.difference:
            self.x, self.y = self.transformer.fit(self.x, self.y)

        # split into train/val/test sets
        self.x_train, self.x_val, self.x_test, = data_utils.train_val_test_split(self.x, 12, 12)
        self.y_train, self.y_val, self.y_test = data_utils.train_val_test_split(self.y, 12, 12)

    def get_data_params(self):
        return self.data_params

    def check_data_params(self):
        if not self.is_data_set:
            raise ValueError('Data has not been set!')

    def set_params(self, **params):
        # clear memory
        K.clear_session()
        map(clear_session, [10] * 10)

        # deal with data params
        self.check_data_params()
        data_params = self.get_data_params()

        params['x_vars'] = len(self.data_params['vars'][0])
        params['x_lags'] = data_params['x_lags']
        params['y_vars'] = len(self.data_params['vars'][1])
        params['y_lags'] = data_params['y_lags']

        super(ForecastRegressor, self).set_params(**params)

    def get_output_lags(self):
        return self.y.shape[1] / len(self.y_vars)

    def _get_data_fold(self, fold):
        if fold == 'train':
            return self.x_train, self.y_train
        elif fold == 'val':
            return self.x_val, self.y_val
        elif fold == 'test':
            return self.x_test, self.y_test
        else:
            raise ValueError('Set must be train, val or test')

    def _fit(self, x, y, **kwargs):
        self.check_data_params()
        self.is_fitted = True

        # if self.difference:
        #     x, y = self.transformer.transform(x, y)

        return super(ForecastRegressor, self).fit(x, y, **kwargs)

    def _predict(self, x, y, **kwargs):
        # check params are set and fit if not fitted
        self.check_data_params()
        if not self.is_fitted:
            self.fit()

        # filter kwargs for predict
        kwargs = self.filter_sk_params(ForecastModel.predict, kwargs)

        # # difference
        # if self.difference:
        #     x, y = self.transformer.transform(x, y)

        # predict
        y_pred = self.model.predict(x, **kwargs)

        # # inverse difference
        # if self.difference:
        #     y_pred = self.transformer.inverse_transform(y_pred, y, recursive=False)

        # # average output lags if multiple
        # if self.get_output_lags() > 1:
        #     y_pred = lag_average(y_pred, self.get_output_lags())
        #     y_pred = y_pred.T

        return y_pred

    def _forecast(self, x, y, **kwargs):
        self.check_data_params()
        if not self.is_fitted:
            self.fit()

        kwargs = self.filter_sk_params(ForecastModel.forecast, kwargs)

        # if self.difference:
        #     x, y = self.transformer.transform(x, y)

        y_fcast = self.model.forecast(x, y, **kwargs)

        # if self.difference:
        #     y_fcast = self.transformer.inverse_transform(y_fcast, y, recursive=True)

        # # average output lags if multiple
        # if self.get_output_lags() > 1:
        #     y_fcast = lag_average(y_fcast, self.get_output_lags())
        #     y_fcast = y_fcast.T

        return y_fcast

    def _loss_function(self, y, y_pred):
        loss = K.eval(self.model.loss_functions[0](y.T, y_pred))
        if self.is_multioutput:
            sm = np.sum(loss)
            loss = [sm] + list(loss)

        return loss

    def _evaluate_prediction(self, x, y, **kwargs):
        # average lags if multi lag output
        # if self.get_output_lags() > 1:
        #     y = lag_average(y, self.get_output_lags())

        y_pred = self._predict(x, y, **kwargs)

        loss = self._loss_function(y, y_pred)
        return loss

    def _evaluate_forecast(self, x, y, **kwargs):
        # if self.get_output_lags() > 1:
        #     y = lag_average(y, self.get_output_lags())

        y_pred = self._forecast(x, y, **kwargs)
        loss = self._loss_function(y, y_pred)
        return loss

    def fit(self, **kwargs):
        return self._fit(self.x_train, self.y_train, **kwargs)

    def predict(self, fold, **kwargs):
        x, y = self._get_data_fold(fold)
        return self._predict(x, y, **kwargs)

    def forecast(self, fold, **kwargs):
        x, y = self._get_data_fold(fold)
        return self._forecast(x, y, **kwargs)

    def evaluate_prediction(self, fold, refit=False, **kwargs):
        if refit:
            self.fit()

        x, y = self._get_data_fold(fold)
        loss = self._evaluate_prediction(x, y, **kwargs)
        return loss

    def evaluate_forecast(self, fold, refit=False, **kwargs):
        if refit:
            self.fit()

        x, y = self._get_data_fold(fold)
        loss = self._evaluate_forecast(x, y, **kwargs)
        return loss

    def validate(self, cv_splits, num_runs):
        x = pd.concat([self.x_train, self.x_val], axis=0)
        y = pd.concat([self.y_train, self.y_val], axis=0)

        if cv_splits == 1:
            splitter = PredefinedSplit([-1 for _ in range(len(x) - 12)] + [0 for _ in range(12)])
            split = list(splitter.split(X=x, y=y)) * num_runs
        else:
            splitter = TimeSeriesSplit(cv_splits, max_train_size=len(x) - 12)
            split = list(splitter.split(X=x, y=y)) * num_runs

        res = map(self._validate, split)
        res = np.mean(list(res), axis=0)

        # K.clear_session()

        return res[0][0], res[1][0]

    def _validate(self, split):

        x = self.x
        y = self.y

        x_train = x.iloc[split[0], :]
        x_val = x.iloc[split[1], :]
        y_train = y.iloc[split[0], :]
        y_val = y.iloc[split[1], :]

        self._fit(x_train, y_train)
        tr_res = self._evaluate_prediction(x_train, y_train)
        vl_res = self._evaluate_prediction(x_val, y_val)

        if self.is_multioutput:
            tr_res = [tr_res[0]]
            vl_res = [vl_res[0]]

        return [vl_res, tr_res]

    def evaluate_losses(self, num_runs):
        variables = self.y_vars
        pred_keys = ['train pred', 'val pred', 'test pred']
        fcast_keys = ['train fcast', 'val fcast', 'test fcast']
        sets = ['train', 'val', 'test']

        result = OrderedDict()

        for pred_key, fcast_key, set in zip(pred_keys, fcast_keys, sets):
            pred_fcast = list(map(self._evaluate_losses, [set] * num_runs))
            pred_res = [i[0] for i in pred_fcast]
            fcast_res = [i[1] for i in pred_fcast]

            # pred_res = list(map(self.evaluate_prediction, [set] * num_runs, [True] * num_runs))
            result[pred_key] = np.mean(np.squeeze(pred_res), axis=0)

            # fcast_res = list(map(self.evaluate_forecast, [set] * num_runs, [True] * num_runs))
            result[fcast_key] = np.mean(np.squeeze(fcast_res), axis=0)

            # K.clear_session()

        if self.is_multioutput:
            result = pd.DataFrame(result, index=['total'] + variables)
        else:
            result = pd.DataFrame(result, index=variables)

        return result

    def _evaluate_losses(self, fold):
        self.fit()
        pred = self.evaluate_prediction(fold)
        fcast = self.evaluate_forecast(fold)
        return (pred, fcast)

    def _get_estimates(self, forecast=False):

        if forecast:
            pred_func = self.forecast
            labels = ['train forecast', 'val forecast', 'test forecast']
        else:
            pred_func = self.predict
            labels = ['train prediction', 'val prediction', 'test prediction']

        num_vars = len(self.y_vars)
        if self.get_output_lags() > 1:
            y = pd.DataFrame(lag_average(self.y, self.get_output_lags()), index=self.y.index,
                             columns=self.y.columns.levels[0])
        else:
            y = self.y

        # y = pd.concat([self.y_train, self.y_val, self.y_test], axis=0)
        sets = ['train', 'val', 'test']
        data_series = [self.x_train, self.x_val, self.x_test]
        predictions = []

        # true y
        temp = pd.DataFrame(y.values, index=y.index, columns=['true values'] * num_vars)
        predictions.append(np.split(temp, num_vars, axis=1))

        for set, series, label in zip(sets, data_series, labels):
            temp = pd.DataFrame(pred_func(set).T, index=series.index,
                                columns=[label] * num_vars)
            predictions.append(np.split(temp, num_vars, axis=1))

        predictions = __builtin__.map(list, zip(*predictions))

        for i in range(len(predictions)):
            predictions[i] = pd.concat(predictions[i], axis=1)

        return predictions

    def get_predictions(self):
        prediction = self._get_estimates()
        return prediction

    def get_forecasts(self):
        forecast = self._get_estimates(forecast=True)
        return forecast

    def get_predictions_and_forecasts(self):
        predictions = self.get_predictions()
        forecasts = self.get_forecasts()
        return predictions, forecasts


def lag_average(data, lags):
    if isinstance(data, pd.DataFrame):
        matrix = data.values
    else:
        matrix = data.copy()

    if len(matrix.shape) == 2:
        vars = matrix.shape[1] / lags
        split = np.split(matrix, vars, axis=1)
        matrix = np.array(split)
    else:
        vars = matrix.shape[0]

    for i in range(matrix.shape[2]):
        matrix[:, :, [i]] = shift(matrix[:, :, [i]], (0, -i, 0), cval=np.nan)

    matrix = np.nanmean(matrix, 2)
    matrix = np.reshape(matrix, (-1, vars))

    if isinstance(data, pd.DataFrame):
        columns = pd.MultiIndex.from_tuples([data.columns[i * lags] for i in range(vars)])
        matrix = pd.DataFrame(matrix, index=data.index, columns=columns)
    return matrix


def model(x_vars, y_vars, x_lags, y_lags, neurons):
    from keras import layers, losses
    from forecast_models import create_input_layers, create_output_layers
    inputs, layer = create_input_layers(x_vars, x_lags)

    layer = layers.Dense(neurons, activation='relu')(layer)

    outputs = create_output_layers(y_vars, y_lags, layer)

    model = ForecastModel(inputs=inputs, outputs=outputs)
    model.compile('adam', losses.mse)
    return model


def main():
    from matplotlib import pyplot as plt
    params = OrderedDict()
    params['neurons'] = 6
    params['epochs'] = 10
    params['batch_size'] = 10

    data_params1 = OrderedDict()
    data_params1['country'] = 'EA'
    data_params1['vars'] = (['CPI'], ['CPI'])
    data_params1['x_lags'] = 2
    data_params1['y_lags'] = 2

    data_params2 = OrderedDict()
    data_params2['country'] = 'EA'
    data_params2['vars'] = (['CPI', 'GDP'], ['CPI'])
    data_params2['x_lags'] = 2
    data_params2['y_lags'] = 2

    data_params3 = OrderedDict()
    data_params3['country'] = 'EA'
    data_params3['vars'] = (['CPI', 'GDP'], ['CPI', 'GDP'])
    data_params3['x_lags'] = 2
    data_params3['y_lags'] = 2

    for data_params in [data_params1, data_params2, data_params3]:
        wrapper = ForecastRegressor(model, data_params, params)
        wrapper.set_params(**params)
        print wrapper.predict('val').shape
        print wrapper.forecast('val').shape


if __name__ == '__main__':
    main()
