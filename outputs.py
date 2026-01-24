from abc import ABC, abstractmethod

KEY_CSV = 'csv'
KEY_CSV_FILENAME = 'filename'
KEY_MYSQL = 'mysql'
KEY_MYSQL_CONNECTIONINFOS = 'connectioninfos'
KEY_MYSQL_TABLENAME = 'tablename'
KEY_HTML = 'html'
KEY_HTML_TEMPLATE = 'template'
KEY_HTML_FILENAME = 'filename'

DEFAULT_OUTPUT_DEFINITIONS = {
  KEY_CSV: lambda output_config, headers: CsvResultsWriter(output_config, headers),
  KEY_MYSQL: lambda output_config, headers: MySqlResultsWriter(output_config, headers),
  KEY_HTML: lambda output_config, headers: HtmlResultsWriter(output_config, headers)
}

class ResultsWriterFactory:
  def __init__(self, output_definitions=None):
    self.output_definitions = output_definitions if output_definitions else DEFAULT_OUTPUT_DEFINITIONS
  def create(self, outputsconfig, headers):
    if len(outputsconfig) > 1: return PipelineResultsWriter(outputsconfig, headers, self)
    else:
      output_format, output_config = next(output_key for output_key in outputsconfig.items())
      if output_format in self.output_definitions:
        return self.output_definitions[output_format](output_config, headers)
      else: raise KeyError(output_format)

class ResultsWriter(ABC):
  def __init__(self, headers):
    self.headers = headers
  @abstractmethod
  def __enter__(self):
    raise NotImplementedError
  @abstractmethod
  def __exit__(self, type, value, tb):
    raise NotImplementedError
  @abstractmethod
  def start_item(self, index):
    raise NotImplementedError
  @abstractmethod
  def write_string(self, value):
    raise NotImplementedError
  @abstractmethod
  def write_int(self, value):
    raise NotImplementedError
  @abstractmethod
  def write_float(self, value):
    raise NotImplementedError
  @abstractmethod
  def write_empty(self):
    raise NotImplementedError
  @abstractmethod
  def end_item(self):
    raise NotImplementedError

class CsvResultsWriter(ResultsWriter):
  def __init__(self, csvconfig, headers):
    super().__init__(headers)
    self.filename = csvconfig[KEY_CSV_FILENAME]
  def __enter__(self):
    self.output = open(self.filename, 'w', encoding='utf8')
    self.output.write(','.join(self.headers) + '\n')
    return self
  def __exit__(self, type, value, tb):
    self.output.close()
  def start_item(self, index):
    self.output.write('%i' % index)
  def write_string(self, value):
    self.output.write(',"%s"' % value)
  def write_int(self, value):
    self.output.write(',%i' % value)
  def write_float(self, value):
    self.output.write(',%f' % value)
  def write_empty(self):
    self.output.write(',')
  def end_item(self):
    self.output.write('\n')

class MySqlResultsWriter(ResultsWriter):
  def __init__(self, mysqlconfig, headers):
    super().__init__(headers)
    self.connectioninfos = mysqlconfig[KEY_MYSQL_CONNECTIONINFOS]
    self.tablename = mysqlconfig[KEY_MYSQL_TABLENAME]
  def __enter__(self):
    from mysql.connector import connect
    self.cnn = connect(**self.connectioninfos)
    self.cursor = self.cnn.cursor()
    columns = ','.join('`%s`' % header for header in self.headers)
    placeholders = ','.join('%s' for header in self.headers)
    self.insertion = 'INSERT INTO `%s` (%s) VALUES (%s)' % (self.tablename, columns, placeholders)
    return self
  def __exit__(self, type, value, tb):
    self.cursor.close()
    self.cnn.close()
  def start_item(self, index):
    self.item_values = (index,)
  def write_string(self, value):
    self.item_values = self.item_values + (value,)
  def write_int(self, value):
    self.item_values = self.item_values + (value,)
  def write_float(self, value):
    self.item_values = self.item_values + (value,)
  def write_empty(self):
    self.item_values = self.item_values + ('NULL',)
  def end_item(self):
    self.cursor.execute(self.insertion, self.item_values)
    self.cnn.commit()

class HtmlResultsWriter(ResultsWriter):
  def __init__(self, htmlconfig, headers):
    super().__init__(headers)
    self.template = htmlconfig[KEY_HTML_TEMPLATE]
    self.filename = htmlconfig[KEY_HTML_FILENAME]
  def __enter__(self):
    from io import StringIO
    from mako.template import Template
    from mako.runtime import Context
    self.data = {
      'headers': self.headers,
      'items': []
    }
    self.engine = Template(filename=self.template)
    self.buffer = StringIO()
    self.context = Context(self.buffer, data=self.data)
    return self
  def __exit__(self, type, value, tb):
    self.item = None
    self.engine.render_context(self.context)
    with open(self.filename, 'w', encoding='utf8') as output:
      output.write(self.buffer.getvalue())
      output.close()
  def start_item(self, index):
    self.item = [index]
  def write_string(self, value):
    self.item.append(str(value).replace('\n', '<br/>'))
  def write_int(self, value):
    self.item.append(value)
  def write_float(self, value):
    self.item.append(value)
  def write_empty(self):
    self.item.append("&nbsp;")
  def end_item(self):
    self.data['items'].append(self.item)

class PipelineResultsWriter(ResultsWriter):
  def __init__(self, outputsconfig, headers, results_writer_factory):
    self.pipeline = []
    for item_format, item_config in outputsconfig.items():
      output_config = { item_format: item_config }
      self.pipeline.append(results_writer_factory.create(output_config, headers))
  def __enter__(self):
    for item in self.pipeline:
      item.__enter__()
    return self
  def __exit__(self, type, value, tb):
    for item in self.pipeline:
      item.__exit__(type, value, tb)
  def start_item(self, index):
    for item in self.pipeline:
      item.start_item(index)
  def write_string(self, value):
    for item in self.pipeline:
      item.write_string(value)
  def write_int(self, value):
    for item in self.pipeline:
      item.write_int(value)
  def write_float(self, value):
    for item in self.pipeline:
      item.write_float(value)
  def write_empty(self):
    for item in self.pipeline:
      item.write_empty()
  def end_item(self):
    for item in self.pipeline:
      item.end_item()
