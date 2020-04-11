from abc import ABC, abstractmethod

KEY_CSV = 'csv'
KEY_CSV_FILENAME = 'filename'
KEY_MYSQL = 'mysql'
KEY_MYSQL_CONNECTIONINFOS = 'connectioninfos'
KEY_MYSQL_TABLENAME = 'tablename'
KEY_HTML = 'html'
KEY_HTML_FILANEME = 'filename'
KEY_HTML_TITLE = 'title'
KEY_HTML_SCRIPTS = 'scripts'
KEY_HTML_STYLES = 'styles'

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
  def end_item(self):
    raise NotImplementedError
  @staticmethod
  def Create(outputsconfig, headers):
    if len(outputsconfig) > 1: return PipelineResultsWriter(outputsconfig, headers)
    else:
      output_format, output_config = next(output_key for output_key in outputsconfig.items())
      if output_format == KEY_CSV: return CsvResultsWriter(output_config, headers)
      elif output_format == KEY_MYSQL: return MySqlResultsWriter(output_config, headers)
      elif output_format == KEY_HTML: return HtmlResultsWriter(output_config, headers)
      else: raise KeyError(output_format)

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
  def end_item(self):
    self.cursor.execute(self.insertion, self.item_values)
    self.cnn.commit()

class HtmlResultsWriter(ResultsWriter):
  def __init__(self, htmlconfig, headers):
    super().__init__(headers)
    self.filename = htmlconfig[KEY_HTML_FILANEME]
    self.title = htmlconfig[KEY_HTML_TITLE] if KEY_HTML_TITLE in htmlconfig else None
    self.scripts = htmlconfig[KEY_HTML_SCRIPTS] if KEY_HTML_SCRIPTS in htmlconfig else []
    self.styles = htmlconfig[KEY_HTML_STYLES] if KEY_HTML_STYLES in htmlconfig else []
  def __enter__(self):
    htmltitle = ("""
    <title>%s</title>""" % self.title) if self.title else ''
    self.output = open(self.filename, 'w', encoding='utf8')
    self.output.write("""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />%s""" % htmltitle)
    for script in self.scripts:
      self.output.write("""
    <script src="%s"></script>""" % script)
    for style in self.styles:
      self.output.write("""
    <link rel="stylesheet" type="text/css" href="%s" />""" % style)
    self.output.write("""
  </head>
  <body>
    <table id="data">
      <thead>
        <tr>""")
    for h in self.headers:
      self.output.write("""
          <th>%s</th>""" % h)
    self.output.write("""
        </tr>
      </thead>""")
    return self
  def __exit__(self, type, value, tb):
    self.output.write("""
    </table>
  </body>
</html>""")
    self.output.close()
  def start_item(self, index):
    self.output.write("""
      <tr>
        <td>%i</td>""" % index)
  def write_string(self, value):
    self.output.write("""
        <td>%s</td>""" % str(value).replace('\n', '<br/>'))
  def write_int(self, value):
    self.output.write("""
        <td>%i</td>""" % value)
  def write_float(self, value):
    self.output.write("""
        <td>%f</td>""" % value)
  def end_item(self):
    self.output.write("""
      </tr>""")

class PipelineResultsWriter(ResultsWriter):
  def __init__(self, outputsconfig, headers):
    self.pipeline = []
    for item_format, item_config in outputsconfig.items():
      output_config = { item_format: item_config }
      self.pipeline.append(ResultsWriter.Create(output_config, headers))
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
  def end_item(self):
    for item in self.pipeline:
      item.end_item()
