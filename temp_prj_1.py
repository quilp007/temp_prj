#!/usr/bin/env python
# coding=utf8

import os, sys, time, datetime
from PyQt5.QtCore import QObject, pyqtSignal, QThread, pyqtSignal, pyqtSlot, QEvent
from PyQt5.QtWidgets import QApplication, QMainWindow 
from PyQt5.QtWidgets import *
from PyQt5 import uic, QtCore

import numpy as np
import shelve
from datetime import datetime
import pandas as pd
import pyqtgraph as pg

import time
import serial
import json
import pymongo

# ------------------------------------------------------------------------------
# config -----------------------------------------------------------------------
# ------------------------------------------------------------------------------

ENABLE_MONGODB = True
server_ip = '211.57.90.83'

userid = 'temp'
passwd = 'temp!'

mongo_port = 27017
mqtt_port = 1883

DEVICE_ID = 'temp_db_1'

mongodb_temperature_col = None
mongodb_humidity_col = None
mongodb_signup_col = None

# table row number
ROW_COUNT = 30  # limit: 30
ROW_COUNT_2 = 3  # limit: 3

# graph x size
PLOT_X_SIZE = 360  # graph's x size
x_size = 200  # graph's x size

# use global variable!!!!!!!!!!!!!!!
USE_GLOBAL_VARIABLE = False
# USE_GLOBAL_VARIABLE = True

LINE_NUM = 16  # thermal film line

RES_REF = 20

P_RES_REF = 20
P_ERROR_REF = 0.20  # 5%
P_ERROR_LIMIT = 0.40  # 12.5%
P_PLOT_MIN_MAX = 0.50  # 15%

ERROR_REF = 0.10  # 5%
# ERROR_LIMIT = 0.1     # 10%
ERROR_LIMIT = 0.20  # 12.5%
PLOT_MIN_MAX = 0.25  # 15%

"""
P_RES_REF = 875

P_ERROR_REF = 0.05  # 5%
P_ERROR_LIMIT = 0.125  # 12.5%
P_PLOT_MIN_MAX = 0.15  # 15%

ERROR_REF = 0.05  # 5%
# ERROR_LIMIT = 0.1     # 10%
ERROR_LIMIT = 0.125  # 12.5%
PLOT_MIN_MAX = 0.15  # 15%
"""

# config for keysight 34461a
display = True  # 34461a display On(True)/Off(False)
DMM_RES_RANGE = 100000  # 34461a range (ohm, not k ohm)
DMM_RESOLUTION = 2
# COM_PORT = 'com4'
COM_PORT = '/dev/tty.usbmodem141301'
BAUD_RATE = 9600

# READ_DELAY = 0.01
READ_DELAY = 0.005
ENABLE_BLANK_LINE = False
BLANK_DATA_COUNT = 20

# ------------------------------------------------------------------------------
# TEST_DATA = True  # if read data from excel
TEST_DATA = False # if read data from 34461a

if not TEST_DATA:
    serialDev = serial.Serial(COM_PORT, BAUD_RATE)

form_class = uic.loadUiType('temp_prj_1.ui')[0]


# --------------------------------------------------------------
# [THREAD] RECEIVE from PLC (receive from PLC)
# --------------------------------------------------------------
class THREAD_RECEIVE_Data(QThread):
    intReady = pyqtSignal(float, float)
    to_excel = pyqtSignal(str, float)

    @pyqtSlot()
    def __init__(self):
        super(THREAD_RECEIVE_Data, self).__init__()
        self.time_format = '%Y%m%d_%H%M%S'

        if TEST_DATA:
            self.test_data = pd.read_excel('./20211223_154032.xlsx')
            # self.data_count_start = 11000
            self.data_count_start = 1
            # self.data_count_start = 3400
            self.data_count_end = 17400

            self.data_count = self.data_count_start

        self.__suspend = False
        self.__exit = False
        self.log_flag = False

    def run(self):
        while True:
            ### Suspend ###
            while self.__suspend:
                time.sleep(0.5)

            _time = datetime.now()
            _time = _time.strftime(self.time_format)

            if TEST_DATA:
                read = self.test_data[1][self.data_count]
                self.data_count += 1
                if self.data_count > self.data_count_end:  # 5000:
                    self.data_count = self.data_count_start # 1700

                time.sleep(READ_DELAY)
            else:
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

                temp = float(temp)
                humi = float(humi)

            # read = RES_REF
            print(f'{_time} > temp: {temp}  humi: {humi}')

            self.intReady.emit(temp, humi)

            if self.log_flag:
                self.to_excel.emit(_time, read)

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


ptr = 0
count= 0
state = 0


class CustomAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super(CustomAxis, self).__init__(*args, **kwargs)
        self.tick_labels = {0: '-360', 60: '-300', 120: '-240', 180: '-180', 240: '-120', 300: '-60', 360: '0'}

    def tickStrings(self, values, scale, spacing):
        # values 배열을 역순으로 처리하여 레이블 생성
        # 예를 들어, 값이 [0, 1, 2, 3, 4]로 들어오면 ['4', '3', '2', '1', '0']로 레이블을 반환
        # return [str(value) for value in reversed(values)]
        return [self.tick_labels.get(value, '') for value in values]


class qt(QMainWindow, form_class):
    def __init__(self):
        # QMainWindow.__init__(self/conf)
        # uic.loadUiType('qt_test2.ui', self)[0]

        super().__init__()
        self.setupUi(self)
        # self.setWindowFlags(Qt.FramelessWindowHint)

        self.res_ref = self.p_res_ref = self.line_num = 0
        self.p_error_ref = 0
        self.p_error_upper = self.p_error_lower = 0
        self.p_error_limit_upper = self.p_error_limit_lower = 0
        self.p_plot_upper = self.p_plot_lower = 0
        self.error_upper = self.error_lower = 0
        self.error_limit_upper = self.error_limit_lower = 0
        self.plot_upper = self.plot_lower = 0

        self.loadParam()
        print('RES_REF: ', RES_REF)
        self.setParam()

        # lcdNum click event connect to function
        self.clickable(self.lcdNum_line_num).connect(lambda: self.input_lcdNum(self.lcdNum_line_num))
        self.clickable(self.lcdNum_r_ref).connect(lambda: self.input_lcdNum(self.lcdNum_r_ref))         # k ohm
        self.clickable(self.lcdNum_p_r_ref).connect(lambda: self.input_lcdNum(self.lcdNum_p_r_ref))
        self.clickable(self.lcdNum_error_ref).connect(lambda: self.input_lcdNum(self.lcdNum_error_ref))
        self.clickable(self.lcdNum_error_limit).connect(lambda: self.input_lcdNum(self.lcdNum_error_limit))
        self.clickable(self.lcdNum_dmm_r_range).connect(lambda: self.input_lcdNum(self.lcdNum_dmm_r_range))
        self.clickable(self.lcdNum_dmm_resolution).connect(lambda: self.input_lcdNum(self.lcdNum_dmm_resolution))
        self.clickable(self.label_mode).connect(self.mode_change)

        self.btn_main.clicked.connect(lambda: self.main_button_function(self.btn_main))
        self.btn_parameter.clicked.connect(lambda: self.main_button_function(self.btn_parameter))
        self.btn_alarm.clicked.connect(lambda: self.main_button_function(self.btn_alarm))
        self.btn_alarm_list.clicked.connect(lambda: self.main_button_function(self.btn_alarm_list))
        self.btn_debug.clicked.connect(lambda: self.main_button_function(self.btn_debug))

        self.btn_start.clicked.connect(lambda: self.btn_34461a(self.btn_start))
        self.btn_stop.clicked.connect(lambda: self.btn_34461a(self.btn_stop))
        self.btn_close.clicked.connect(lambda: self.btn_34461a(self.btn_close))

        self.data = np.linspace(-np.pi, np.pi, x_size)
        self.y1_1 = np.zeros(len(self.data))
        self.y1_2 = np.zeros(len(self.data))

        # self.y2_1 = np.sin(self.data)
        self.y2_1 = [np.nan] * PLOT_X_SIZE
        self.y2_2 = [np.nan] * PLOT_X_SIZE

        self.y3_1 = [np.nan] * 700

        # self.plot(self.data, self.y1_1)

        # Updating Plot
        self.p6 = self.graphWidget_2.addPlot(title="Res")
        self.curve1_1 = self.p6.plot(pen='g')
        self.curve1_2 = self.p6.plot(pen='r')
        self.p6.setGeometry(0, 0, x_size, 5)

        self.p6.setYRange(self.plot_upper, self.plot_lower, padding=0)

        self.drawLine(self.p6, self.error_lower, 'y')
        self.drawLine(self.p6, self.error_upper, 'y')
        self.drawLine(self.p6, self.error_limit_lower, 'r')
        self.drawLine(self.p6, self.error_limit_upper, 'r')

        # self.graphWidget.nextRow()

        axis = CustomAxis(orientation='bottom')
        self.p7 = self.graphWidget.addPlot(title="Temp.", axisItems={'bottom': axis})
        self.curve2_1 = self.p7.plot(pen='g')
        self.curve2_2 = self.p7.plot(pen='y')

        self.p7.setYRange(self.p_plot_upper, self.p_plot_lower, padding=0)

        axis = self.p7.getAxis('bottom')  # X 축 객체를 가져옴
        axis.setTickSpacing(major=60, minor=10)
        self.p7.showGrid(x=True, y=True, alpha=0.5)

        # self.drawLine(self.p7, self.p_error_lower, 'y')
        # self.drawLine(self.p7, self.p_error_upper, 'y')
        # self.drawLine(self.p7, self.p_error_limit_lower, 'r')
        # self.drawLine(self.p7, self.p_error_limit_upper, 'r')

        # DEBUG GRAPH
        self.p8 = self.graphWidget_3.addPlot(title="DEBUG")
        self.curve3_1 = self.p8.plot(pen='g')
        self.curve3_2 = self.p8.plot(pen='r')
        self.p8.setGeometry(0, 0, 700, 5)

        self.p8.setYRange(self.plot_upper, self.plot_lower, padding=0)
        # self.p8.setYRange(100000, 1000, padding=0)
        # self.p8.setYRange(50000, 1000, padding=0)

        self.drawLine(self.p8, self.error_lower, 'y')
        self.drawLine(self.p8, self.error_upper, 'y')
        self.drawLine(self.p8, self.error_limit_lower, 'r')
        self.drawLine(self.p8, self.error_limit_upper, 'r')


        self.timer = QtCore.QTimer()
        self.timer.setInterval(10)
        # self.timer.timeout.connect(self.update_func_1)

        # self.timer.timeout.connect(self.sine_plot)

        self.timer.start()

        if TEST_DATA:
            self.counter = x_size

        self.counter = x_size

        self.first_flag = 1

        self.thread_rcv_data = THREAD_RECEIVE_Data()
        self.thread_rcv_data.intReady.connect(self.update_func)
        self.thread_rcv_data.to_excel.connect(self.to_excel_func)
        self.thread_rcv_data.start()

        self.resist_data = []
        # self.writer = pd.ExcelWriter('./data.xlsx')

        self.log_flag = False


        self.measure_mode = True    # resistance mode

        self.main_button_function(self.btn_main)


    def setParam(self):
        self.res_ref    = RES_REF
        self.p_res_ref  = P_RES_REF
        self.line_num   = LINE_NUM

        self.p_error_upper = self.p_res_ref + self.p_res_ref * P_ERROR_REF  # + 5%
        self.p_error_lower = self.p_res_ref - self.p_res_ref * P_ERROR_REF  # - 5%

        self.p_error_limit_upper = self.p_res_ref + self.p_res_ref * P_ERROR_LIMIT  # + 10%
        self.p_error_limit_lower = self.p_res_ref - self.p_res_ref * P_ERROR_LIMIT  # - 10%

        self.p_plot_upper = self.p_res_ref + self.p_res_ref * P_PLOT_MIN_MAX  # + 15%
        self.p_plot_lower = self.p_res_ref - self.p_res_ref * P_PLOT_MIN_MAX  # - 15%

        self.error_upper = self.res_ref + self.res_ref * ERROR_REF  # + 5%
        self.error_lower = self.res_ref - self.res_ref * ERROR_REF  # - 5%

        self.error_limit_upper = self.res_ref + self.res_ref * ERROR_LIMIT  # + 10%
        self.error_limit_lower = self.res_ref - self.res_ref * ERROR_LIMIT  # - 10%

        self.plot_upper = self.res_ref + self.res_ref * PLOT_MIN_MAX  # + 15%
        self.plot_lower = self.res_ref - self.res_ref * PLOT_MIN_MAX  # - 15%


    def loadParam(self):
        global RES_REF, LINE_NUM, P_RES_REF, ERROR_REF, ERROR_LIMIT, P_ERROR_REF, P_ERROR_LIMIT, DMM_RES_RANGE, DMM_RESOLUTION
        if not USE_GLOBAL_VARIABLE:
            try:
                with shelve.open('config') as f:
                    LINE_NUM = int(f['line_num'])
                    RES_REF = int(f['r_ref'])*1000
                    P_RES_REF = int(f['p_r_ref'])
                    ERROR_REF = int(f['error_ref'])/100     # 1st line
                    ERROR_LIMIT = int(f['error_limit'])/100 # 2nd line

                    P_ERROR_REF = ERROR_REF
                    P_ERROR_LIMIT = ERROR_LIMIT

                    DMM_RES_RANGE = int(f['dmm_r_range'])*1000
                    DMM_RESOLUTION = int(f['dmm_resolution'])
            except Exception as e:
                print('exception: ', e)

        self.lcdNum_line_num.display(LINE_NUM)
        self.lcdNum_r_ref.display(RES_REF/1000)
        self.lcdNum_p_r_ref.display(P_RES_REF)
        self.lcdNum_error_ref.display(ERROR_REF*100)
        self.lcdNum_error_limit.display(ERROR_LIMIT*100)
        self.lcdNum_dmm_r_range.display(DMM_RES_RANGE/1000)
        self.lcdNum_dmm_resolution.display(DMM_RESOLUTION)


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
        global LINE_NUM, ERROR_REF, ERROR_LIMIT, RES_REF, P_RES_REF, DMM_RES_RANGE, DMM_RESOLUTION
        # item = ('16, '17', '18')
        # text, ok = QInputDialog.getItem(self, 'input', 'select input', item, 0, False)
        # text, ok = QInputDialog.getint(self, 'input', 'input number')
        text, ok = QInputDialog.getInt(self, 'input', 'input number')
        if ok:
            if lcdNum == self.lcdNum_line_num:
                LINE_NUM = text
                self.save_var('line_num', text)
            elif lcdNum == self.lcdNum_r_ref:
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
            elif lcdNum == self.lcdNum_dmm_r_range:
                DMM_RES_RANGE = text
                self.save_var('dmm_r_range', text)
            elif lcdNum == self.lcdNum_dmm_resolution:
                DMM_RESOLUTION = text
                self.save_var('dmm_resolution', text)

            lcdNum.display(text)


    def drawLine(self, plot_name, val, color):
        line = pg.InfiniteLine(angle=0, movable=True, pen=color)
        line.setValue(val)
        plot_name.addItem(line, ignoreBounds=True)


    def stParam(self, lcdNum):
        with shelve.open('config.db') as f:
            if lcdNum == self.lcdNum_line_num:
                f['LINE_NUM'] = self.lcdNum_line_num.value()


    def to_excel_func(self, _time, data):
        tt = [_time, data]
        self.resist_data.append(tt)
        print(tt)


    def insert_log(self, temp):
        time_text = time.strftime('%y.%m.%d_%H:%M:%S', time.localtime(time.time()))
        log_text = time_text + '   ' + str(temp) + '°C'
        self.textEdit_log.append(log_text)

        result = mongodb_temperature_col.insert_one({'timestamp': datetime.now(), 'temp': temp})

    def update_func(self, temp, humi):
        global ptr
        global count
        if temp > 100: temp = 100
        elif temp < 0: temp = 0

        self.y3_1 = np.roll(self.y3_1, -1)
        self.y3_1[-1] = temp
        self.curve3_1.setData(self.y3_1)

        # self.mean_value_plot(temp, humi)
        if count % 10 == 0:
            if ptr < PLOT_X_SIZE:
                self.y2_1[ptr] = temp
                ptr+=1
            else:
                self.y2_1 = np.roll(self.y2_1, -1)
                self.y2_1[-1] = temp

            self.curve2_1.setData(self.y2_1)
        
            self.y2_2 = np.roll(self.y2_2, -1)
            self.y2_2[-1] = humi
            self.curve2_2.setData(self.y2_2)

            self.insert_log(temp)

        count+=1

        self.lcdNum_TEMP.display("{:.1f}".format(temp))
        self.lcdNum_HUMI.display("{:.1f}".format(humi))



    def mean_value_plot(self, mean_value, two_sheets_p_res):
        self.y2_1 = np.roll(self.y2_1, -1)
        self.y2_1[-1] = mean_value
        self.curve2_1.setData(self.y2_1)

        self.y2_2 = np.roll(self.y2_2, -1)
        self.y2_2[-1] = two_sheets_p_res
        self.curve2_2.setData(self.y2_2)

    def sine_plot(self):
        # self.g_plotWidget.plot(hour, temperature)
        # curve = self.graphWidget_2.plot(pen='y')
        self.y2_1 = np.roll(self.y2_1, -1)
        self.y2_1[-1] = np.sin(self.data[self.counter % x_size])*5 + 20
        self.curve2_1.setData(self.y2_1)

        mean_value = 10 + np.round(self.y2_1[-1], 1) / 10
        if self.counter % 50 == 0:
            self.lcdNum_T_SV_CH1.display("{:.1f}".format(mean_value))
        # print('y2_1: ', mean_value)

        self.counter += 1


    def btn_34461a(self, button):
        if button == self.btn_start:
            self.thread_rcv_data.myResume()
            self.thread_rcv_data.log_flag = True
        elif button == self.btn_stop:
            self.thread_rcv_data.log_flag = False
            # self.thread_rcv_data.mySuspend()
            df1 = pd.DataFrame(self.resist_data)
            _time = datetime.now()
            _time = _time.strftime(self.thread_rcv_data.time_format)

            with pd.ExcelWriter(_time + '.xlsx') as writer:
                df1.to_excel(writer, _time + '.xlsx')

            self.resist_data = []

        elif button == self.btn_close:
            self.thread_rcv_data.close()

    # button setting for MAIN PAGE CHANGE
    def main_button_function(self, button):
        global gLogon

        self.btn_main.setStyleSheet("background-color: #dedede; border: 0px")
        self.btn_parameter.setStyleSheet("background-color: #dedede; border: 0px")
        self.btn_alarm.setStyleSheet("background-color: #dedede; border: 0px")
        self.btn_alarm_list.setStyleSheet("background-color: #dedede; border: 0px")
        self.btn_debug.setStyleSheet("background-color: #dedede; border: 0px")

        if button == self.btn_main:
            self.stackedWidget.setCurrentWidget(self.sw_MAIN)
            self.btn_main.setStyleSheet("background-color: lime; border: 0px")
        elif button == self.btn_parameter:
            self.stackedWidget.setCurrentWidget(self.sw_PARAMETER)
            self.btn_parameter.setStyleSheet("background-color: lime; border: 0px")
        elif button == self.btn_alarm:
            self.stackedWidget.setCurrentWidget(self.sw_ALARM)
            self.btn_alarm.setStyleSheet("background-color: lime; border: 0px")
        elif button == self.btn_alarm_list:
            self.stackedWidget.setCurrentWidget(self.sw_ALARM_LIST)
            self.btn_alarm_list.setStyleSheet("background-color: lime; border: 0px")
        elif button == self.btn_debug:
            self.stackedWidget.setCurrentWidget(self.sw_DEBUG)
            self.btn_debug.setStyleSheet("background-color: lime; border: 0px")
        # elif button == self.btn_logon:
        #     if gLogon == True:
        #         # self.Logoff_func()
        #     else:
        #         # self.stackedWidget.setCurrentWidget(self.sw_LOGON)


def initMongoDB():
    global mongodb_temperature_col
    global mongodb_humidity_col
    global mongodb_signup_col

    if ENABLE_MONGODB:
        conn = pymongo.MongoClient('mongodb://' + server_ip,
                                   username=userid,
                                   password=passwd)
                                   # authSource=DEVICE_ID)

        db = conn.get_database(DEVICE_ID)
        mongodb_temperature_col = db.get_collection('temperature')
        mongodb_humidity_col = db.get_collection('humidity')
        mongodb_signup_col = db.get_collection('signup')

def run():
    app = QApplication(sys.argv)
    widget = qt()
    widget.show()
    # widget.update_func_1()

    sys.exit(app.exec_())


if __name__ == "__main__":
    initMongoDB()
    run()
