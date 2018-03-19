#!/usr/bin/env python
"""Generate FIO Benchmark Report.

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
"""

import json
import re
import os
import click
import pandas as pd


class FioTestReporter():
    """FIO Test Reporter.

    This class used to generate the fio test report. As basic functions:
    1. It loads the raw data from from fio log files;
    2. It analyse the raw data and extract performance KPIs from raw data;
    3. It generates the report DataFrame and dump to a CSV file;

    Attributes:
        raw_data_list: the list to store raw data.
        perf_kpi_list: the list to store performance KPI tuples.
        df_report: a DataFrame to store the test report.

    """

    # The list of raw data, the item is loaded from fio log file.
    # Each item is a full data source (raw data) in Python dict format.
    raw_data_list = []

    # The list of performance KPIs, which are extracted from the raw data.
    # Each item represents a single fio test results in Python dict format.
    perf_kpi_list = []

    # The DataFrame to store performance KPIs for reporting, which is powered
    # by Pandas.
    df_report = None

    def _get_raw_data_from_fio_log(self, data_file):
        """Get the raw data from a specified fio log file.

        This function open a specified fio log file and read the first json
        block which is expected to be generated by the fio --output=json/json+.
        Then it converts this block into Python dict format and returns it.

        Function byteify will convert the unicode string to bytes.

        Args:
            data_file: string, the path to the fio log file.

        Returns:
            This function returns a tuple like (result, raw_data):
            result:
                0: Passed
                1: Failed
            raw_data:
                The raw data in Python dict format.

        Raises:
            1. Error while handling fio log file
            2. Error while handling the new json file

        """

        def byteify(inputs):
            """Convert unicode to utf-8 string."""
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
        if data_file == '':
            print 'Missing required params: data_file'
            return (1, None)

        # Get the offsets of the first json block
        try:
            with open(data_file, 'r') as f:
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
        except Exception, err:
            print 'Error while handling fio log file: %s' % err
            return (1, None)

        # Extract the json block into a new file and get the raw_data
        if begin >= end:
            print 'Cannot found validate json block in file: %s' % data_file
            return (1, None)

        try:
            with open(data_file + '.json', 'w') as json_file:
                json_file.writelines(file_content[begin:end + 1])
            with open(data_file + '.json', 'r') as json_file:
                json_data = json.load(json_file)
                raw_data = byteify(json_data)
        except Exception, err:
            print 'Error while handling the new json file: %s' % err
            return (1, None)

        os.unlink(data_file + '.json')
        return (0, raw_data)

    def load_raw_data_from_fio_logs(self, params={}):
        """Load raw data from fio log files.

        This function loads raw data from a sort of fio log files and stores
        the raw data (in Python dict format) into self.raw_data_list.

        Args:
            params: dict
                result_path: string, the path where the fio log files located.

        Returns:
            0: Passed
            1: Failed

        Updates:
            self.raw_data_list: store all the raw data;

        """
        # Parse required params
        if 'result_path' not in params:
            print 'Missing required params: params[result_path]'
            return 1

        # load raw data from files
        for basename in os.listdir(params['result_path']):
            filename = params['result_path'] + '/' + basename

            if filename.endswith('.fiolog') and os.path.isfile(filename):
                (result, raw_data) = self._get_raw_data_from_fio_log(filename)
                if result == 0:
                    self.raw_data_list.append(raw_data)

        return 0

    def _get_kpis_from_raw_data(self, raw_data):
        """Get KPIs from a specified raw data.

        This function get the performance KPIs from a specified tuple of raw
        data. It converts the units and format the values so that people can
        read them conveniently.

        Args:
            raw_data: dict, the specified raw data.

        Returns:
            This function returns a tuple like (result, perf_kpi):
            result:
                0: Passed
                1: Failed
            perf_kpi:
                The performance KPIs in Python dict format.

        Raises:
            1. Error while extracting performance KPIs

        """
        # Parse required params
        if raw_data == '':
            print 'Missing required params: raw_data'
            return (1, None)

        # Get the performance KPIs
        perf_kpi = {}

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

    def calculate_performance_kpis(self, params={}):
        """Calculate performance KPIs.

        This function calculates performance KPIs from self.raw_data_list and
        stores the performance KPI tuples into self.perf_kpi_list.

        As data source, the following attributes should be ready to use:
        1. self.raw_data_list: the list of raw data (Python dict format)

        Args:
            params: dict
                None

        Returns:
            0: Passed
            1: Failed

        Updates:
            self.perf_kpi_list: store the performance KPI tuples.

        """
        # Calculate performance KPIs
        for raw_data in self.raw_data_list:
            (result, perf_kpi) = self._get_kpis_from_raw_data(raw_data)
            if result == 0:
                self.perf_kpi_list.append(perf_kpi)
            else:
                return 1

        return 0

    def _create_report_dataframe(self):
        """Create report DataFrame.

        This function creates the report DataFrame by reading the performance
        KPIs list.

        As data source, the following attributes should be ready to use:
        1. self.perf_kpi_list: the list of performance KPIs.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Create report DataFrame from self.perf_kpi_list
        self.df_report = pd.DataFrame(
            self.perf_kpi_list,
            columns=[
                'backend', 'driver', 'format', 'rw', 'bs', 'iodepth',
                'numjobs', 'round', 'bw', 'iops', 'lat', 'util'
            ])

        # Rename the columns of the report DataFrame
        self.df_report.rename(
            columns={
                'backend': 'Backend',
                'driver': 'Driver',
                'format': 'Format',
                'rw': 'RW',
                'bs': 'BS',
                'iodepth': 'IODepth',
                'numjobs': 'Numjobs',
                'round': 'Round',
                'bw': 'BW(MiB/s)',
                'iops': 'IOPS',
                'lat': 'LAT(ms)',
                'util': 'Util(%)'
            },
            inplace=True)

        return None

    def _format_report_dataframe(self):
        """Format report DataFrame.

        This function sorts and formats the report DataFrame.

        As data source, the following attributes should be ready to use:
        1. self.df_report: the report DataFrame.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Sort the report DataFrame and reset its index
        self.df_report = self.df_report.sort_values(by=[
            'Backend', 'Driver', 'Format', 'RW', 'BS', 'IODepth', 'Numjobs'
        ])
        self.df_report = self.df_report.reset_index().drop(columns=['index'])

        # Format the KPI values
        self.df_report = self.df_report.round(4)

        return None

    def generate_report_dataframe(self):
        """Generate the report DataFrame.

        This function generates the report DataFrame by reading the
        performance KPIs list.

        As data source, the following attributes should be ready to use:
        1. self.perf_kpi_list: the list of performance KPIs.

        Updates:
            self.df_report: the report DataFrame.

        """
        # Create DataFrame
        self._create_report_dataframe()

        # Format DataFrame
        self._format_report_dataframe()

        return None

    def report_dataframe_to_csv(self, params={}):
        """Dump the report DataFrame to a csv file.

        As data source, the self.df_report should be ready to use.

        Args:
            params: dict
                report_csv: string, the csv file to dump report DataFrame to.

        Returns:
            0: Passed
            1: Failed

        Raises:
            1. Error while dumping to csv file

        """
        # Parse required params
        if 'report_csv' not in params:
            print 'Missing required params: params[report_csv]'
            return 1

        # Write the report to the csv file
        try:
            print 'Dumping data into csv file "%s"...' % params['report_csv']
            content = self.df_report.to_csv()
            with open(params['report_csv'], 'w') as f:
                f.write(content)
            print 'Finished!'

        except Exception, err:
            print 'Error while dumping to csv file: %s' % err
            return 1

        return 0


@click.command()
@click.argument('result_path')
@click.argument('report_csv')
def generate_fio_test_report(result_path, report_csv):
    """Generate FIO test report."""
    ftr = FioTestReporter()

    ret = ftr.load_raw_data_from_fio_logs({'result_path': result_path})
    if ret != 0:
        exit(1)

    ret = ftr.calculate_performance_kpis()
    if ret != 0:
        exit(1)

    ftr.generate_report_dataframe()

    ret = ftr.report_dataframe_to_csv({'report_csv': report_csv})
    if ret != 0:
        exit(1)

    exit(0)


if __name__ == '__main__':

    generate_fio_test_report()

    exit(0)
