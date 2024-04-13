#!/usr/bin/env python
# coding=utf8

import os, sys, time
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSignal, pyqtSlot, QEvent
from PyQt5.QtWidgets import QApplication, QMainWindow 
from PyQt5.QtWidgets import *
from PyQt5 import uic, QtCore

import numpy as np
import shelve
from datetime import datetime, timedelta
import pandas as pd
import pyqtgraph as pg

import time
import serial
import json
import pymongo

# ------------------------------------------------------------------------------
# config -----------------------------------------------------------------------
# ------------------------------------------------------------------------------

# MongoDB config
ENABLE_MONGODB = True
server_ip = '211.57.90.83'

userid = 'temp'
passwd = 'temp!'

mongo_port = 27017
mqtt_port = 1883

DEVICE_ID = 'temp_db_1'

mongodb_signup_col = None
mongodb_data_col = None
mongodb_list = None
mongodb_dict = {}

DIR_CHECK_DATA = './output/check_data/'
DIR_AUTO_DATA = './output/auto_data/'

# must be match DEVICE_ID and DB NAME
DEVICE_ID = 'temp_db_5'

# MODE config
# debug mode: display all tabs
DEBUG_MODE = True

# pc mode: 
# 1. display monitoring tab, check data tab 
# 2. not receive serial data (disable)
# True: PC mode, False: raspberry pi mode
PC_MODE = False

RASPBERRY_PI = False    # change serial port
if RASPBERRY_PI == True:
    PC_MODE = False
    DEBUG_MODE = False

# use global variable!!!!!!!!!!!!!!!
USE_GLOBAL_VARIABLE = False
# USE_GLOBAL_VARIABLE = True

# serial config
# COM_PORT = 'com4'
if RASPBERRY_PI:
    COM_PORT = '/dev/ttyACM0'
else:
    COM_PORT = '/dev/tty.usbmodem1412301'
BAUD_RATE = 9600

if not PC_MODE:
    serialDev = serial.Serial(COM_PORT, BAUD_RATE)

# graph config
TEMP_PLOT_UPPER = 30 
TEMP_PLOT_LOWER = 15 

HUMI_PLOT_UPPER = 40
HUMI_PLOT_LOWER = 0 

NUM_OF_GRAPH_ROW    = 2
NUM_OF_GRAPH_COLUMN = 4

# graph x size
PLOT_X_SIZE = 720 + 1  # graph's x size

# time to save data to mongodb, display monitoring graph
SAVE_PERIOD = 60 * 2 * 1000   # second

# ------------------------------------------------------------------------------
# TEST_DATA = True  # if read data from excel
TEST_DATA = False # if read data from 34461a


form_class = uic.loadUiType('temp_prj.ui')[0]

# --------------------------------------------------------------
# [THREAD] RECEIVE from PLC (receive from PLC)
# --------------------------------------------------------------
class THREAD_RECEIVE_Data(QThread):
    intReady = pyqtSignal(float, float)
    intPlot  = pyqtSignal()

    @pyqtSlot()
    def __init__(self):
        super(THREAD_RECEIVE_Data, self).__init__()
        self.time_format = '%Y%m%d_%H%M%S'

        self.__suspend = False
        self.__exit = False

        self.temp =15 
        self.humi =15 
        self._time = 0

        self.timer_ = QtCore.QTimer()
        self.timer_.setInterval(SAVE_PERIOD)
        self.timer_.timeout.connect(self.timeout_func)
        self.timer_.start()


    def timeout_func(self):
        if not PC_MODE:
            mongodb_data_col.insert_one({'timestamp': self._time, 'temp': self.temp, 'humi': self.humi})
        self.intPlot.emit()


    def run(self):
        while True:
            ### Suspend ###
            while self.__suspend:
                time.sleep(0.5)

            if not PC_MODE:
                rawserial = serialDev.readline()
                cookedserial = rawserial.decode('utf-8').strip('\r\n')
                try:
                    jsonData = json.loads(cookedserial)
                except Exception as e:
                    print(f'error: {e}')
                    continue

                print(jsonData)
                temp = jsonData['Temperature']
                humi = jsonData['Humidity']
                print(f'Humidity: {humi}')
                print('Temperature: ', temp)

                self.temp = temp
                self.humi = humi

                self._time = datetime.now()
                _time_str = self._time.strftime(self.time_format)

                print(f'{_time_str} > temp: {self.temp}  humi: {self.humi}')
                self.intReady.emit(self.temp, self.humi)
            else:
                time.sleep(1)

            ### Exit ###
            if self.__exit:
                break

    def mySuspend(self):
        self.__suspend = True

    def myResume(self):
        self.__suspend = False

    def myExit(self):
        self.__exit = True

    def close(self):
        self.mySuspend()
        time.sleep(0.1)
        self.ks_34461a.close()

class CustomAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super(CustomAxis, self).__init__(*args, **kwargs)
        # self.tick_labels = {0: '-24', 120: '-20', 240: '-16', 360: '-12', 480: '-8', 600: '-4', 720: '0'}
        # self.tick_labels = {0: '0', 120: '4', 240: '8', 360: '12', 480: '16', 600: '20', 720: '24'}
        self.tick_labels = {0: '0', 30: '1', 60: '2', 90: '3', 120: '4', 150: '5', 180: '6', 210: '7', 240: '8', 270: '9', 300: '10', 330: '11',\
                        360: '12', 390: '13', 420: '14', 450: '15', 480: '16', 510: '17', 540: '18', 570: '19', 600: '20', 630: '21', 660: '22', 690: '23', 720: '24'}

    def tickStrings(self, values, scale, spacing):
        # values 배열을 역순으로 처리하여 레이블 생성
        # 예를 들어, 값이 [0, 1, 2, 3, 4]로 들어오면 ['4', '3', '2', '1', '0']로 레이블을 반환
        # return [str(value) for value in reversed(values)]
        return [self.tick_labels.get(value, '') for value in values]

class CustomAxis2(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super(CustomAxis2, self).__init__(*args, **kwargs)
        self.tick_labels = {0: '-12', 60: '-11', 120: '-10', 180: '-9', 240: '-8', 300: '-7', 360: '-6', 420: '-5', 480: '-4', 540: '-3', 600: '-2', 660: '-1', 720: '0'}

    def tickStrings(self, values, scale, spacing):
        return [self.tick_labels.get(value, '') for value in values]


class qt(QMainWindow, form_class):
    def __init__(self):
        # QMainWindow.__init__(self/conf)
        # uic.loadUiType('qt_test2.ui', self)[0]

        super().__init__()
        self.setupUi(self)
        # self.setWindowFlags(Qt.FramelessWindowHint)

        # self.loadParam()

        # lcdNum click event connect to function
        self.clickable(self.lcdNum_r_ref).connect(lambda: self.input_lcdNum(self.lcdNum_r_ref))         # k ohm
        self.clickable(self.lcdNum_p_r_ref).connect(lambda: self.input_lcdNum(self.lcdNum_p_r_ref))
        self.clickable(self.lcdNum_error_ref).connect(lambda: self.input_lcdNum(self.lcdNum_error_ref))
        self.clickable(self.lcdNum_error_limit).connect(lambda: self.input_lcdNum(self.lcdNum_error_limit))
        self.clickable(self.label_mode).connect(self.mode_change)

        self.btn_check_data.clicked.connect(self.check_data)
        self.btn_excel.clicked.connect(self.save_data_to_excel)

        self.y2_1 = [np.nan] * PLOT_X_SIZE
        self.y2_2 = [np.nan] * PLOT_X_SIZE

        self.y3_1 = [np.nan] * PLOT_X_SIZE
        self.y3_2 = [np.nan] * PLOT_X_SIZE

        # self.curve = np.zeros((2, 3, 2)) 
        # 2x3x2 크기의 리스트 초기화
        self.curve = [[[None for _ in range(NUM_OF_GRAPH_ROW)] for _ in range(NUM_OF_GRAPH_COLUMN)] for _ in range(2)]

        self.current_row = 0
        
        self.CLEAR_FLAG = False

        # for MongoDB data
        self.results_check_data = []
        self.results_name = None

        #----------------- Humidity Plot
        axis = CustomAxis(orientation='bottom')
        self.p6 = self.graphWidget_2.addPlot(title="Humidity", axisItems={'bottom': axis})
        self.curve1_1 = self.p6.plot(pen='g')
        self.curve1_2 = self.p6.plot(pen='y')

        self.p6.setYRange(HUMI_PLOT_UPPER, HUMI_PLOT_LOWER, padding=0)

        axis = self.p6.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=30, minor=30)
        self.p6.showGrid(x=True, y=True, alpha=0.5)

        # self.graphWidget.nextRow()

        #----------------- Temperature Plot
        axis = CustomAxis(orientation='bottom')
        self.p7 = self.graphWidget.addPlot(title="Temperature", axisItems={'bottom': axis})
        self.curve2_1 = self.p7.plot(pen='r')
        self.curve2_2 = self.p7.plot(pen='y')

        self.p7.setYRange(TEMP_PLOT_UPPER, TEMP_PLOT_LOWER, padding=0)

        axis = self.p7.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=30, minor=30)
        self.p7.showGrid(x=True, y=True, alpha=0.5)

        #----------------- [데이터 확인] DB data -> Temperature Plot
        axis = CustomAxis(orientation='bottom')
        self.db_plot_1 = self.graphWidget_4.addPlot(title="DB Temperature", axisItems={'bottom': axis})
        self.curve_db_1_1 = self.db_plot_1.plot(pen='r')
        self.curve_db_1_2 = self.db_plot_1.plot(pen='y')

        self.db_plot_1.setYRange(TEMP_PLOT_UPPER, TEMP_PLOT_LOWER, padding=0)

        axis = self.db_plot_1.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=30, minor=30)
        self.db_plot_1.showGrid(x=True, y=True, alpha=0.5)

        #----------------- [데이터 확인] DB data -> Humidity Plot
        axis = CustomAxis(orientation='bottom')
        self.db_plot_2 = self.graphWidget_5.addPlot(title="DB Humidity", axisItems={'bottom': axis})
        self.curve_db_2_1 = self.db_plot_2.plot(pen='g')
        self.curve_db_2_2 = self.db_plot_2.plot(pen='y')

        self.db_plot_2.setYRange(HUMI_PLOT_UPPER, HUMI_PLOT_LOWER, padding=0)

        axis = self.db_plot_2.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=30, minor=30)
        self.db_plot_2.showGrid(x=True, y=True, alpha=0.5)

        # DEBUG GRAPH
        axis = CustomAxis2(orientation='bottom')
        self.p8 = self.graphWidget_3.addPlot(title=DEVICE_ID, axisItems={'bottom': axis})
        self.curve3_1 = self.p8.plot(pen='r')
        self.curve3_2 = self.p8.plot(pen='g')

        self.p8.setYRange(TEMP_PLOT_UPPER, HUMI_PLOT_LOWER, padding=0)
        axis = self.p8.getAxis('bottom')  # X 축 객체를 가져옴
        # axis.setTickSpacing(major=120, minor=60)
        axis.setTickSpacing(major=60, minor=60)
        self.p8.showGrid(x=True, y=True, alpha=0.5)

        #----------------- PC Main graphWidget
        for idx, db_name in enumerate(mongodb_list):
            self.add_plot(db_name, int(idx/NUM_OF_GRAPH_COLUMN), int(idx%NUM_OF_GRAPH_COLUMN))
        #----------------- PC Main graphWidget

        # for idx in range(2, 6):
        #     db_name = 'test' + str(idx + 1)
        #     self.add_plot(db_name, int(idx/3), int(idx%3))

        # for idx in range(0, 6):
        #     r = int(idx/3) 
        #     c = int(idx%3)

        #     if self.current_row != r:
        #         self.gW_pc_1.nextRow()

        #     if idx < len(mongodb_list):
        #         db_name = mongodb_list[idx]
        #         self.add_plot(db_name, r, c)
        #     else:
        #         # self.gW_pc_1.addItem(pg.GraphicsLayout(), r, c)
        #         db_name = 'test' + str(idx + 1)
        #         self.add_plot(db_name, r, c)

        #     self.current_row = r


        self.thread_rcv_data = THREAD_RECEIVE_Data()
        self.thread_rcv_data.intReady.connect(self.update_func)
        self.thread_rcv_data.intPlot.connect(self.check_data_main)
        self.thread_rcv_data.start()

        self.measure_mode = True    # resistance mode

        self.label_device.setText(DEVICE_ID)

        self.comboBox_year.activated.connect(self.update_month_combobox)
        self.comboBox_month.activated.connect(self.update_day_combobox)
        self.comboBox_day.activated.connect(self.check_data)
        self.comboBox_db.activated.connect(self.load_years_set_date)

        for item in mongodb_list:
            self.comboBox_db.addItem(item, item)
        self.comboBox_db.setCurrentIndex(0)

        self.load_years_set_date()

        self.tabWidget.setTabVisible(5, False)
        if PC_MODE:
            self.tabWidget.setTabVisible(0, False)
            self.tabWidget.setTabVisible(3, False)
            self.tabWidget.setTabVisible(4, False)
        else:
            self.tabWidget.setTabVisible(1, False)
            self.tabWidget.setTabVisible(2, False)

        if DEBUG_MODE:
            self.tabWidget.setTabVisible(0, True)
            self.tabWidget.setTabVisible(1, True)
            self.tabWidget.setTabVisible(2, True)
            self.tabWidget.setTabVisible(3, True)
            self.tabWidget.setTabVisible(4, True)

        self.check_data_main()

    def add_plot(self, pTitle, row, col):
        # if self.current_row != row:
        #     self.gW_pc_1.nextRow()

        axis = CustomAxis(orientation='bottom')
        self.plot = self.gW_pc_1.addPlot(title=pTitle, axisItems={'bottom': axis}, row = row, col = col)
        self.curve[row][col][0] = self.plot.plot(pen='r')
        self.curve[row][col][1] = self.plot.plot(pen='g')

        self.plot.setYRange(TEMP_PLOT_UPPER, HUMI_PLOT_LOWER, padding=0)

        axis = self.plot.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=120, minor=30)
        self.plot.showGrid(x=True, y=True, alpha=0.5)

        # self.current_row = row


    def loadParam(self):
        global RES_REF, P_RES_REF, ERROR_REF, ERROR_LIMIT, P_ERROR_REF, P_ERROR_LIMIT
        if not USE_GLOBAL_VARIABLE:
            try:
                with shelve.open('config') as f:
                    RES_REF = int(f['r_ref'])*1000
                    P_RES_REF = int(f['p_r_ref'])
                    ERROR_REF = int(f['error_ref'])/100     # 1st line
                    ERROR_LIMIT = int(f['error_limit'])/100 # 2nd line

                    P_ERROR_REF = ERROR_REF
                    P_ERROR_LIMIT = ERROR_LIMIT
            except Exception as e:
                print('exception: ', e)

        self.lcdNum_r_ref.display(RES_REF/1000)
        self.lcdNum_p_r_ref.display(P_RES_REF)
        self.lcdNum_error_ref.display(ERROR_REF*100)
        self.lcdNum_error_limit.display(ERROR_LIMIT*100)


    def clickable(self, widget):
        class Filter(QObject):
            clicked = pyqtSignal()  # pyside2 사용자는 pyqtSignal() -> Signal()로 변경

            def eventFilter(self, obj, event):

                if obj == widget:
                    if event.type() == QEvent.MouseButtonRelease:
                        if obj.rect().contains(event.pos()):
                            self.clicked.emit()
                            # The developer can opt for .emit(obj) to get the object within the slot.
                            return True
                return False
        filter = Filter(widget)
        widget.installEventFilter(filter)
        return filter.clicked


    def save_var(self, key, value):
        with shelve.open('config.db') as f:
            f[key] = value


    def mode_change(self):
        item = ('Resistance', 'Current')
        text, ok = QInputDialog.getItem(self, 'MODE', 'select Mode', item, 0, False)
        if ok:
            if text == 'Resistance':
                self.measure_mode = True
            else:
                self.measure_mode = False

            self.label_mode.setText(text)


    def input_lcdNum(self, lcdNum):
        global ERROR_REF, ERROR_LIMIT, RES_REF, P_RES_REF
        text, ok = QInputDialog.getInt(self, 'input', 'input number')
        if ok:
            if lcdNum == self.lcdNum_r_ref:
                RES_REF = text
                self.save_var('r_ref', text)
            elif lcdNum == self.lcdNum_p_r_ref:
                P_RES_REF = text
                self.save_var('p_r_ref', text)
            elif lcdNum == self.lcdNum_error_ref:
                ERROR_REF = text
                self.save_var('error_ref', text)
            elif lcdNum == self.lcdNum_error_limit:
                ERROR_LIMIT = text
                self.save_var('error_limit', text)

            lcdNum.display(text)


    def insert_log(self, temp, humi):
        time_text = time.strftime('%y.%m.%d_%H:%M:%S', time.localtime(time.time()))
        log_text = time_text + '   ' + str(temp) + '°C' + '   ' + str(humi) + '%'
        self.textEdit_log.append(log_text)


    def update_func(self, temp, humi):
        if temp > 100: temp = 100
        elif temp < 0: temp = 0

        self.mean_value_plot(temp, humi)

        symbolSizes = [1] * len(self.y3_1)  # 과거 데이터 점 크기
        symbolSizes[-1] = 7 # 현재 데이터 점 크기

        self.y3_1[-1] = temp
        self.curve3_1.setData(self.y3_1, symbol='o', symbolSize=symbolSizes, symbolBrush=('r'))
        self.y3_1 = np.roll(self.y3_1, -1)

        self.y3_2[-1] = humi
        self.curve3_2.setData(self.y3_2, symbol='o', symbolSize=symbolSizes, symbolBrush=('g'))
        self.y3_2 = np.roll(self.y3_2, -1)

        self.insert_log(temp, humi)

        self.lcdNum_TEMP.display("{:.1f}".format(temp))
        self.lcdNum_HUMI.display("{:.1f}".format(humi))


    def mean_value_plot(self, temp_value, humi_value):
        today = datetime.now()
        hour = today.hour
        min = today.minute

        if hour == 0:
            if min < 1 and self.CLEAR_FLAG == False:
                self.y2_1 = [np.nan] * PLOT_X_SIZE
                self.y2_2 = [np.nan] * PLOT_X_SIZE

                day_before = today - timedelta(days=1)
                self.check_data(day_before.year, day_before.month, day_before.day)
                self.save_data_to_excel()

                self.CLEAR_FLAG = True

            if min == 1:
                self.CLEAR_FLAG = False


        position = int(hour * 30 + min / 2)

        symbolSizes = [1] * len(self.y3_1)  # 과거 데이터 점 크기
        symbolSizes[position] = 7 # 현재 데이터 점 크기

        self.y2_1[position] = temp_value
        self.curve2_1.setData(self.y2_1, symbol='o', symbolSize=symbolSizes, symbolBrush=('r'))

        self.y2_2[position] = humi_value
        self.curve1_1.setData(self.y2_2, symbol='o', symbolSize=symbolSizes, symbolBrush=('g'))


    def data_to_plot(self, data, key, curve_db):
        db_data = [np.nan] * PLOT_X_SIZE
        for item in data:
            #print(item['timestamp'], item[key])
            tt = item[key]
            hour = item['timestamp'].hour
            min = item['timestamp'].minute
            
            position = int(hour * 30 + min / 2)
            db_data[position] = tt
            # print(key, tt)

        curve_db.setData(db_data)


    def load_years_set_date(self):
        self.comboBox_year.clear()

        mongodb_name = self.comboBox_db.currentData()
        mongodb_data_col = mongodb_dict[mongodb_name]['data_col']

        # 년도 데이터 추출
        pipeline = [
            {"$group": {"_id": {"year": {"$year": "$timestamp"}}}},
            {"$sort": {"_id.year": 1}}
        ]
        years = mongodb_data_col.aggregate(pipeline)

        for year in years:
            print(type(year))
            self.comboBox_year.addItem(str(year['_id']['year']), year['_id']['year'])

        # first time, no db data
        if self.comboBox_year.count() == 0:
            self.comboBox_year.clear()
            self.comboBox_month.clear()
            self.comboBox_day.clear()
            self.curve_db_1_1.setData(np.array([]), np.array([]))
            self.curve_db_2_1.setData(np.array([]), np.array([]))
            return

        # set recent year
        self.comboBox_year.setCurrentIndex(self.comboBox_year.count() - 1)

        # set recent month
        self.update_month_combobox()
        self.comboBox_month.setCurrentIndex(self.comboBox_month.count() -1)

        # set recent day
        self.update_day_combobox()
        self.comboBox_day.setCurrentIndex(self.comboBox_day.count() -1)

        # set db comboBox 
        # self.comboBox_db.addItems(mongodb_list)
        self.check_data()


    def update_month_combobox(self):
        self.comboBox_month.clear()
        selected_year = self.comboBox_year.currentData()

        mongodb_name = self.comboBox_db.currentData()
        mongodb_data_col = mongodb_dict[mongodb_name]['data_col']

        # 선택된 년도에 해당하는 월 데이터를 조회
        pipeline = [
            {"$match": {"$expr": {"$eq": [{"$year": "$timestamp"}, selected_year]}}},
            {"$group": {"_id": {"month": {"$month": "$timestamp"}}}},
            {"$sort": {"_id.month": 1}}
        ]
        months = mongodb_data_col.aggregate(pipeline)

        for month in months:
            self.comboBox_month.addItem(str(month['_id']['month']), month['_id']['month'])


    def update_day_combobox(self):
        self.comboBox_day.clear()
        selected_year = self.comboBox_year.currentData()
        selected_month = self.comboBox_month.currentData()

        mongodb_name = self.comboBox_db.currentData()
        mongodb_data_col = mongodb_dict[mongodb_name]['data_col']

        # 선택된 년도와 월에 해당하는 일 데이터를 조회
        pipeline = [
            {"$match": {
                "$and": [
                    {"$expr": {"$eq": [{"$year": "$timestamp"}, selected_year]}},
                    {"$expr": {"$eq": [{"$month": "$timestamp"}, selected_month]}}
                ]
            }},
            {"$group": {"_id": {"day": {"$dayOfMonth": "$timestamp"}}}},
            {"$sort": {"_id.day": 1}}
        ]
        days = mongodb_data_col.aggregate(pipeline)

        for day in days:
            self.comboBox_day.addItem(str(day['_id']['day']), day['_id']['day'])


    # [데이터 확인]
    def check_data(self, year=None, month=None, day=None):
        display_flag = False
        if day==None:
            display_flag = True

        if display_flag:
            year    = self.comboBox_year.currentData()
            month   = self.comboBox_month.currentData()
            day     = self.comboBox_day.currentData()

        start_date = datetime(year, month, day)
        end_date = datetime(year, month, day+1)

        mongodb_name = self.comboBox_db.currentData()
        mongodb_data_col = mongodb_dict[mongodb_name]['data_col']

        self.results_name = "{}_{}_{}_{}".format(mongodb_name, year, month, day)
        
        self.results_check_data.clear()
        self.results_check_data = list(mongodb_data_col.find({
            'timestamp': {  # 'timestamp'는 날짜 및 시간 데이터를 저장하는 필드의 이름입니다.
                '$gte': start_date,
                '$lt': end_date
            }
        }))

        if display_flag:
            self.data_to_plot(self.results_check_data, 'temp', self.curve_db_1_1)
            self.data_to_plot(self.results_check_data, 'humi', self.curve_db_2_1)


    def check_data_main(self):
        start_date = datetime.now()
        start_date = datetime(start_date.year, start_date.month, start_date.day)
        end_date = datetime(start_date.year, start_date.month, start_date.day + 1)

        for idx, mongodb_name in enumerate(mongodb_list):
            mongodb_data_col = mongodb_dict[mongodb_name]['data_col']
        
            results = list(mongodb_data_col.find({
                'timestamp': {  # 'timestamp'는 날짜 및 시간 데이터를 저장하는 필드의 이름입니다.
                    '$gte': start_date,
                    '$lt': end_date
                }
            }))
            self.data_to_plot(results, 'temp', self.curve[int(idx/NUM_OF_GRAPH_COLUMN)][int(idx%NUM_OF_GRAPH_COLUMN)][0])
            self.data_to_plot(results, 'humi', self.curve[int(idx/NUM_OF_GRAPH_COLUMN)][int(idx%NUM_OF_GRAPH_COLUMN)][1])


    def save_data_to_excel(self, name = None, data = None):
        df = pd.DataFrame(self.results_check_data)
        df = df.drop(columns=['_id'])

        df.to_csv(DIR_CHECK_DATA + self.results_name+'.csv', index=False, header=True)


def initMongoDB():
    global mongodb_signup_col
    global mongodb_data_col
    global mongodb_list
    global mongodb_dict

    if ENABLE_MONGODB:
        conn = pymongo.MongoClient('mongodb://' + server_ip,
                                   username=userid,
                                   password=passwd)
                                   # authSource=DEVICE_ID)
        db = conn.get_database(DEVICE_ID)
        mongodb_data_col = db.get_collection('data')
        mongodb_signup_col = db.get_collection('signup')

        mongodb_list = conn.list_database_names()

        for mongodb_db in mongodb_list:
            db = conn.get_database(mongodb_db)
            data_col = db.get_collection('data')
            signup_col = db.get_collection('signup')

            mongodb_dict[mongodb_db] = {
                'db': db,
                'data_col': data_col,
                'signup_col': signup_col
            }

def check_directory():
    dir_path = [DIR_AUTO_DATA, DIR_CHECK_DATA]

    for dir in dir_path:
        if not os.path.exists(dir):
            os.makedirs(dir)
            print(f"Directory '{dir}' was created.")
        else:
            print(f"Directory '{dir}' already exists.")

def run():
    app = QApplication(sys.argv)
    widget = qt()
    widget.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    initMongoDB()
    check_directory()
    run()
