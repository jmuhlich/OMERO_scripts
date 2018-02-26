import sys
import os
import ConfigParser
from omero.util.sessions import SessionsStore
from omero.gateway import BlitzGateway
from omero.sys import ParametersI
from csv import writer, QUOTE_NONE


class OMEROConnectionManager:
    ''' Basic management of an OMERO Connection. Methods which make use of
        a connection will attempt to connect if connect was not already
        successfuly executed '''

    def __init__(self, config_file=None):

        # Set the connection as not established
        self.conn = None

        self.SUUID = None
        self.HOST = None
        self.PORT = None
        self.USERNAME = None
        self.PASSWORD = None

        # If config_file not specified, first see if there's an active OMERO
        # CLI session.
        if config_file is None:
            store = SessionsStore()
            session_props = store.get_current()
            self.HOST, self.USERNAME, self.SUUID, self.PORT = session_props

        # config_file specified, or no active session. Continue with reading
        # connection params from the config file.
        if config_file is not None or self.SUUID is None:

            # Normalize file path.
            if config_file is None:
                config_file = '~/.omero/config'
            config_file = os.path.expanduser(config_file)

            # Check config file exists.
            if not (os.path.exists(config_file)
                    and os.path.isfile(config_file)):
                sys.stderr.write('No active OMERO CLI session and '
                                 'configuration file {} does not '
                                 'exist\n'.format(config_file))
                sys.exit(1)

            # Check permisisons on config file.
            if os.stat(config_file).st_mode & 0077:
                sys.stderr.write('Configuration file contains private '
                                 'credentials and must not be accessible by '
                                 'other users. Please run:\n\n'
                                 '    chmod 600 {}\n\n'.format(config_file))
                sys.exit(1)

            # Read the credentials file.
            config = ConfigParser.RawConfigParser()
            config.read(config_file)
            self.HOST = config.get('OMEROCredentials', 'host')
            self.PORT = config.getint('OMEROCredentials', 'port')
            self.USERNAME = config.get('OMEROCredentials', 'username')
            self.PASSWORD = config.get('OMEROCredentials', 'password')

    def connect(self):
        ''' Create an OMERO Connection '''

        # If connection already established just return it
        if self.conn is not None:
            return self.conn

        # Initialize the connection. At least HOST and PORT will be defined,
        # but USERNAME and PASSWORD may be None if we are connecting to an
        # existing session via its uuid.
        self.conn = BlitzGateway(username=self.USERNAME,
                                 passwd=self.PASSWORD,
                                 host=self.HOST,
                                 port=self.PORT)

        # Connect. If USERNAME and PASSWORD are None then SUUID must be
        # defined.
        connected = self.conn.connect(sUuid=self.SUUID)

        # Check that the connection was established
        if not connected:
            sys.stderr.write('Error: Connection not available, '
                             'please check your user name and password.\n')
            sys.exit(1)
        return self.conn

    def disconnect(self):
        ''' Terminate the OMERO Connection '''
        if self.conn:
            self.conn.seppuku(softclose=True)
            self.conn = None

    def hql_query(self, query, params=None):
        ''' Execute the given HQL query and return the results. Optionally
            accepts a parameters object.
            For conveniance, will unwrap the OMERO types '''

        # Connect if not already connected
        if self.conn is None:
            self.connect()

        if params is None:
            params = ParametersI()

        # Set OMERO Group to -1 to query across all available data
        self.conn.SERVICE_OPTS.setOmeroGroup(-1)

        # Get the Query Service
        qs = self.conn.getQueryService()

        # Execute the query
        rows = qs.projection(query, params, self.conn.SERVICE_OPTS)

        # Unwrap the query results
        unwrapped_rows = []
        for row in rows:
            unwrapped_row=[]
            for column in row:
                if column is None:
                    unwrapped_row.append(None)
                else:
                    unwrapped_row.append(column.val)
            unwrapped_rows.append(unwrapped_row)

        return unwrapped_rows

    def __del__(self):
        self.disconnect()


def write_csv(rows, filename, header=None):
    ''' Write a CSV File with the given header and rows '''

    # If there is a header to be written, ensure that it is the same length
    # as the first row.
    if header is not None and len(rows) > 0 and len(rows[0]) != len(header):
        raise ValueError('Header does not have the same number of columns '
                         'as the rows')

    # Write the CSV File
    with open(filename, 'wb') as csvfile:
        row_writer = writer(csvfile, quoting=QUOTE_NONE)
        if header is not None:
            row_writer.writerow(header)
        row_writer.writerows(rows)


def well_from_row_col(row, column):
    ''' Return a meaningful Well from a well row and column. E.g.
        Row=4, Column=3 will result in a Well of D2 '''

    # Convert row to character, Making use of ASCII character set numbering,
    # where A-Z is 65-90. Also increment column as it is indexed from zero
    # in the database, but not in the Well designation
    return '%s%i' % (chr(65 + int(row)), column + 1)
