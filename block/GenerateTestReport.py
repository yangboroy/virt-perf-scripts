#!/usr/bin/env python

# Interface between StoragePerformanceTest.py
# StoragePerformanceTest.py should do:
# 1. the fio outputs should be at least in json+ format
#    the "fio --group_reporting" must be used
# 2. save the fio outputs into *.fiolog
# 3. put all *.fiolog files into ./fio_result/
# 4. empty ./fio_report/ folder
# 5. pass the additional information by "fio --description"
#    a) "driver" - frontend driver, such as SCSI or IDE
#    b) "format" - the disk format, such as raw or xfs
#    c) "round" - the round number, such as 1, 2, 3...
#    d) "backend" - the hardware which data image based on

import json
import re
import os
import prettytable


class FioPerformanceKPIs():
    '''
    Get, deal with and covert the performance KPI data from FIO tools.
    '''

    # The list of raw data, the item is loaded from fio output file.
    # Each item is a full data source (raw data) and it is in json format.
    raw_data_list = []

    # The list of performance KPIs, which are extracted from the raw data.
    # Each item represents a single fio test and it is in python dict format.
    perf_kpi_list = []

    # The table of performance KPIs, which is powered by PrettyTable.
    table = None

    def file_to_raw(self, params={}):
        '''
        This function open a specified fio output file and read the first json block which is expected to be the fio outputs in json/json+ format.
        And convert the json block into the json format in python. With the help of function byteify, it converts the unicode string to bytes.
        '''

        def byteify(inputs):
            '''Convert unicode to utf-8 string.'''
            if isinstance(inputs, dict):
                return {
                    byteify(key): byteify(value)
                    for key, value in inputs.iteritems()
                }
            elif isinstance(inputs, list):
                return [byteify(element) for element in inputs]
            elif isinstance(inputs, unicode):
                return inputs.encode('utf-8')
            else:
                return inputs

        # Parse required params
        if 'data_file' not in params:
            print 'Missing required params: params[data_file]'
            return (1, None)

        # Generate json file with the first json block in data file
        try:
            with open(params['data_file'], 'r') as f:
                file_content = f.readlines()

            # Locate the first json block
            begin = end = num = 0
            while num < len(file_content):
                if re.search(r'^{', file_content[num]):
                    begin = num
                    break
                num += 1
            while num < len(file_content):
                if re.search(r'^}', file_content[num]):
                    end = num
                    break
                num += 1

            # Write the json block into file
            if begin < end:
                with open(params['data_file'] + '.json', 'w') as f:
                    f.writelines(file_content[begin:end + 1])
            else:
                print 'Cannot found validate json block in file: %s' % params[
                    'data_file']
                return (1, None)

        except Exception, err:
            print 'Error while handling data file: %s' % err
            return (1, None)

        try:
            with open(params['data_file'] + '.json', 'r') as json_file:
                json_data = json.load(json_file)
                raw_data = byteify(json_data)
        except Exception, err:
            print 'Error while handling data file: %s' % err
            return (1, None)

        return (0, raw_data)

    def load_raw_data(self, params={}):
        '''
        This function loads json raw data from a sort of fio output files and save them into self.raw_data_list.
        '''

        # Parse required params
        if 'result_path' not in params:
            print 'Missing required params: params[result_path]'
            return 1

        # load raw data from files
        for basename in os.listdir(params['result_path']):
            filename = params['result_path'] + '/' + basename

            if filename.endswith('.fiolog') and os.path.isfile(filename):
                (result, raw_data) = self.file_to_raw({'data_file': filename})
                if result == 0:
                    self.raw_data_list.append(raw_data)

        return 0

    def raw_to_kpi(self, params={}):
        '''
        This function extracts performance KPIs from a tuple of raw data.
        Coverts the units and format the value so people can read them conveniently.
        '''

        # Parse required params
        if 'raw_data' not in params:
            print 'Missing required params: params[raw_data]'
            return (1, None)

        # Extract the performance KPIs
        perf_kpi = {}
        raw_data = params['raw_data']

        try:
            perf_kpi['rw'] = raw_data['jobs'][0]['job options']['rw']
            perf_kpi['bs'] = raw_data['jobs'][0]['job options']['bs']
            perf_kpi['iodepth'] = raw_data['jobs'][0]['job options']['iodepth']
            perf_kpi['numjobs'] = raw_data['jobs'][0]['job options']['numjobs']

            # The unit of "bw" was "KiB/s", convert to "MiB/s"
            perf_kpi['r-bw'] = raw_data['jobs'][0]['read']['bw'] / 1024.0
            perf_kpi['w-bw'] = raw_data['jobs'][0]['write']['bw'] / 1024.0
            perf_kpi['bw'] = perf_kpi['r-bw'] + perf_kpi['w-bw']

            # The IOPS was a decimal, make it an integer
            perf_kpi['r-iops'] = int(raw_data['jobs'][0]['read']['iops'])
            perf_kpi['w-iops'] = int(raw_data['jobs'][0]['write']['iops'])
            perf_kpi['iops'] = perf_kpi['r-iops'] + perf_kpi['w-iops']

            # The unit of "lat" was "ns", convert to "ms"
            perf_kpi['r-lat'] = raw_data['jobs'][0]['read']['lat_ns'][
                'mean'] / 1000000.0
            perf_kpi['w-lat'] = raw_data['jobs'][0]['write']['lat_ns'][
                'mean'] / 1000000.0
            perf_kpi['lat'] = perf_kpi['r-lat'] + perf_kpi['w-lat']

            # Get util% of the disk
            if len(raw_data['disk_util']) == 1:
                perf_kpi['util'] = raw_data['disk_util'][0]['util']
            else:
                print 'Error while parsing disk_util: length != 1'
                perf_kpi['util'] = 'error'

            # Get additional information
            try:
                dict = eval(raw_data['jobs'][0]['job options']['description'])
                perf_kpi.update(dict)
            except Exception, err:
                print 'Error while parsing additional information: %s' % err

            if 'driver' not in perf_kpi:
                perf_kpi['driver'] = 'n/a'
            if 'format' not in perf_kpi:
                perf_kpi['format'] = 'n/a'
            if 'round' not in perf_kpi:
                perf_kpi['round'] = 'n/a'
            if 'backend' not in perf_kpi:
                perf_kpi['backend'] = 'n/a'

        except Exception, err:
            print 'Error while extracting performance KPIs: %s' % err
            return (1, None)

        return (0, perf_kpi)

    def extracts_perf_kpis(self, params={}):
        '''
        This function extracts performance KPIs from self.raw_data_list and save the tuples into self.perf_kpi_list.
        '''

        # Extracts performance KPIs
        for raw_data in self.raw_data_list:
            (result, perf_kpi) = perf_kpis.raw_to_kpi({'raw_data': raw_data})
            if result == 0:
                self.perf_kpi_list.append(perf_kpi)

        return 0

    def build_table(self, params={}):
        '''
        This function builds self.table by coverting the data in self.perf_kpi_list.
        '''

        # Build the table from self.perf_kpi_list
        try:
            self.table = prettytable.PrettyTable([
                "Backend", "Driver", "Format", "RW", "BS", "IODepth",
                "Numjobs", "Round", "BW(MiB/s)", "IOPS", "LAT(ms)", "Util(%)"
            ])

            for perf_kpi in self.perf_kpi_list:
                self.table.add_row([
                    perf_kpi['backend'], perf_kpi['driver'],
                    perf_kpi['format'], perf_kpi['rw'], perf_kpi['bs'],
                    perf_kpi['iodepth'], perf_kpi['numjobs'],
                    perf_kpi['round'], perf_kpi['bw'], perf_kpi['iops'],
                    perf_kpi['lat'], perf_kpi['util']
                ])

        except Exception, err:
            print 'Error while building self.table: %s' % err
            return 1

        # Format this table
        self.format_table()

        return 0

    def format_table(self, params={}):
        '''
        This function formats the values in self.table so that people can read
        the outputs conveniently. And this action will not damage the data
        inside the table.
        '''

        # Edit global settings
        self.table.float_format = '.4'

        # Edit pre-colume settings
        self.table.float_format['LAT(ms)'] = '.4'

        return 0

    def print_table(self, params={}):
        '''
        This function makes a copy of self.table, defines the appearance and
        print it out to the console.
        '''

        # Parse required params
        if 'table_style' in params:
            valid_inputs = ('DEFAULT', 'MSWORD_FRIENDLY', 'PLAIN_COLUMNS',
                            'plain')
            if params['table_style'] not in valid_inputs:
                print 'Invalid params: params[table_style]: "%s", the valid inputs are: %s' % (
                    params['table_style'], valid_inputs)
                return 1

        # Make a copy of self.table
        my_table = self.table[:]

        # Edit the appearance
        if 'table_style' in params:
            if params['table_style'] == 'DEFAULT':
                my_table.set_style(prettytable.DEFAULT)
            if params['table_style'] == 'MSWORD_FRIENDLY':
                my_table.set_style(prettytable.MSWORD_FRIENDLY)
            if params['table_style'] == 'PLAIN_COLUMNS':
                my_table.set_style(prettytable.PLAIN_COLUMNS)
            if params['table_style'] == 'plain':
                my_table.border = False
                my_table.align = 'l'
                my_table.left_padding_width = 0
                my_table.right_padding_width = 2

        # Print the table
        print my_table

        return 0


if __name__ == '__main__':

    perf_kpis = FioPerformanceKPIs()
    perf_kpis.load_raw_data({'result_path': './block/samples'})
    perf_kpis.extracts_perf_kpis()

    #print 'perf_kpis.perf_kpi_list:', perf_kpis.perf_kpi_list
    perf_kpis.build_table()
    perf_kpis.print_table()

    exit(0)
