from re import search, match as test, findall, IGNORECASE
from lxml import html
from datetime import datetime
from urllib.parse import urljoin

APPLICATION_NAME = 'downdrag'
APPLICATION_CONFIG_FILENAME = 'downdrag.yml'
KEY_DETAILS = 'details'
KEY_DETAILS_TYPE = 'type'
KEY_DETAILS_CONVERSION = 'conversion'
KEY_DETAILS_CONVERSION_PROCESS = 'process'
KEY_DETAILS_CONVERSION_PATTERN = 'pattern'
KEY_DETAILS_CONVERSION_FORMULA = 'formula'
KEY_DETAILS_DEFAULT = 'default'
KEY_DETAILS_SOURCE = 'source'
KEY_PROFILES = 'profiles'
KEY_SCRAPE_TARGET = 'scrape_target'
KEY_QUERIER = 'querier'
KEY_QUERIER_MODE = 'mode'
KEY_OUTPUTS = 'outputs'
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
KEY_URL = 'url'
KEY_PAGERS = 'pagers'
KEY_ITEMS = 'items'
KEY_INFOS = 'infos'
KEY_NAME = 'name'
KEY_FEATURES = 'features'
KEY_EVALUATOR = 'evaluator'
KEY_EVALUATOR_LINK = 'link'
KEY_PATHFINDER = 'pathfinder'
KEY_PATHFINDER_TARGET = 'target'
KEY_PATHFINDER_PATTERN = 'pattern'
KEY_PATHFINDER_INDEXER = 'indexer'
KEY_PATHFINDER_TYPE = 'type'
KEY_PATHFINDER_FORMAT = 'format'
KEY_PATHFINDER_VALUE = 'value'
QUERIER_PLAIN = 'plain'
QUERIER_SECURE = 'secure'
USAGE_TYPES_MULTIPART = { 'schedule': ['%s start', '%s end'] }
MAIN_FIELDS = ['itemindex', 'source', 'index', 'name', 'description', 'extrainfo', 'link']
TARGET_CURRENT = 'current'
TARGET_EXTERNAL = 'external'
TARGET_INDEX = 'index'
TYPE_STRING = 'string'
TYPE_INT = 'int'
TYPE_FLOAT = 'float'
CONVERSION_VALUE = 'value'
CONVERSION_CALCULATE = 'calculate'
CONVERSION_LAYER = 'layer'
CONVERSION_SCHEDULE = 'schedule'
PATHFINDER_TYPE_FULLTEXT = 'fulltext'
PATHFINDER_TYPE_SHOWCASE = 'showcase'
PATHFINDER_FORMAT_NOW = 'now'
PATHFINDER_FORMAT_LIST = 'list'

class DataQuerier(object):
  def __enter__(self):
    raise NotImplementedError
  def __exit__(self, type, value, tb):
    raise NotImplementedError
  def get(self, url):
    raise NotImplementedError
  @staticmethod
  def Create(config):
    querier = config[KEY_QUERIER][KEY_QUERIER_MODE] if KEY_QUERIER in config else QUERIER_PLAIN
    if querier == QUERIER_SECURE: return SecureDataQuerier()
    elif querier == QUERIER_PLAIN: return PlainDataQuerier()
    else: raise KeyError(querier)

class PlainDataQuerier(DataQuerier):
  def __enter__(self):
    from requests import get
    self.getter = get
    return self
  def __exit__(self, type, value, tb):
    pass
  def get(self, url):
    return self.getter(url)

class SecureDataQuerier(DataQuerier):
  def __enter__(self):
    from requests import Session
    from torpy import TorClient
    from torpy.http.adapter import TorHttpAdapter
    self.tor = TorClient()
    self.guard = self.tor.get_guard()
    self.adapter = TorHttpAdapter(self.guard, 3)
    self.request = Session()
    self.request.headers.update({'User-Agent': 'Mozilla/5.0'})
    self.request.mount('http://', self.adapter)
    self.request.mount('https://', self.adapter)
    return self
  def __exit__(self, type, value, tb):
    self.request.close()
    self.guard.close()
  def get(self, url):
    return self.request.get(url)

class ResultsWriter(object):
  def __init__(self, config):
    self.headers = MAIN_FIELDS.copy()
    for detailname, detail in config[KEY_DETAILS].items():
      conversionprocess = detail[KEY_DETAILS_CONVERSION][KEY_DETAILS_CONVERSION_PROCESS]
      if conversionprocess in USAGE_TYPES_MULTIPART:
        for headerformat in USAGE_TYPES_MULTIPART[conversionprocess]:
          self.headers.append(headerformat % detailname)
      else:
        self.headers.append(detailname)
  def __enter__(self):
    raise NotImplementedError
  def __exit__(self, type, value, tb):
    raise NotImplementedError
  def start_item(self, index):
    raise NotImplementedError
  def write_string(self, value):
    raise NotImplementedError
  def write_int(self, value):
    raise NotImplementedError
  def write_float(self, value):
    raise NotImplementedError
  def end_item(self):
    raise NotImplementedError
  @staticmethod
  def Create(config):
    outputs = config[KEY_OUTPUTS]
    if len(outputs) > 1: return PipelineResultsWriter(config)
    else:
      output_format = next(output_key for output_key in outputs.keys())
      if output_format == KEY_CSV: return CsvResultsWriter(config)
      elif output_format == KEY_MYSQL: return MySqlResultsWriter(config)
      elif output_format == KEY_HTML: return HtmlResultsWriter(config)
      else: raise KeyError(output_format)

class CsvResultsWriter(ResultsWriter):
  def __init__(self, config):
    super().__init__(config)
    csvconfig = config[KEY_OUTPUTS][KEY_CSV]
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
  def __init__(self, config):
    super().__init__(config)
    mysqlconfig = config[KEY_OUTPUTS][KEY_MYSQL]
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
  def __init__(self, config):
    super().__init__(config)
    htmlconfig = config[KEY_OUTPUTS][KEY_HTML]
    self.filename = htmlconfig[KEY_HTML_FILANEME]
    self.title = htmlconfig[KEY_HTML_TITLE]
    self.scripts = htmlconfig[KEY_HTML_SCRIPTS]
    self.styles = htmlconfig[KEY_HTML_STYLES]
  def __enter__(self):
    self.output = open(self.filename, 'w', encoding='utf8')
    self.output.write("""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>%s</title>""" % self.title)
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

class PipelineResultsWriter(object):
  def __init__(self, config):
    outputs = config[KEY_OUTPUTS]
    self.pipeline = []
    for item_format, item_config in outputs.items():
      output_config = config.copy()
      output_config[KEY_OUTPUTS] = { item_format: item_config }
      self.pipeline.append(ResultsWriter.Create(output_config))
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

def parse_link(url, link):
  if link.startswith('#'):
    link = url + link
  else:
    link = urljoin(url, link)
  return link

def execute(config):
  now = datetime.now()
  profiles = config[KEY_PROFILES]
  with DataQuerier.Create(config) as querier:
    with ResultsWriter.Create(config) as output:
      itemindex = 0
      for scrape_target, scrape_profile in profiles.items():
        pathfinder = scrape_profile[KEY_PATHFINDER]

        url = scrape_profile[KEY_URL]
        page = querier.get(url)
        tree = html.fromstring(page.content)

        # if KEY_PAGERS in scrape_profile:
        #   pagers = tree.xpath(scrape_profile[KEY_PAGERS])
        #   if pagers:
        #     from selenium.webdriver import Chrome as driver, ChromeOptions as options
        #     args = options()
        #     args.add_argument('--incognito')
        #     args.headless = True
        #     with driver(options=args) as drive:
        #       drive.get(url)
        #       while True:
        #         tabs = drive.find_elements_by_xpath(scrape_profile[KEY_PAGERS])
        #         old_tabs = []
        #         for act in tabs:
        #           if act.value_of_css_property('display') == 'none':
        #             old_tabs.append(act)
        #         tabs = set(tabs) - set(old_tabs)
        #         if not tabs:
        #           break
        #         for act in tabs:
        #           act.click()
        #       page_content = drive.find_element_by_tag_name('html')
        #       tree = html.fromstring(page_content.get_attribute('outerHTML'))

        data = tree.xpath(scrape_profile[KEY_ITEMS])
        index = 0
        for item in data:
          if item is None: continue
          try:
            linkinfos = scrape_profile[KEY_INFOS] if KEY_INFOS in scrape_profile else 'descendant::a'
            link = parse_link(url, str(item.xpath(linkinfos)[0].attrib['href']))
            child = querier.get(link)
            infos = html.fromstring(child.content)
            name = cleanvalue(infos.xpath(scrape_profile[KEY_NAME])[0].split()[0])

            features = infos.xpath(scrape_profile[KEY_FEATURES])
            feature_items = []
            for feat in features:
              if feat is None: continue
              match = search(scrape_profile[KEY_EVALUATOR], feat)
              if not match: continue
              value = match.group(1).replace('-', ',').strip()
              if value.strip() != '':
                feature_items.append(value)
            description = ','.join(feature_items)

            extrainfo = ''
            target_details = infos
            evaluatortarget = pathfinder[KEY_PATHFINDER_TARGET]
            isexternaltarget = evaluatortarget == TARGET_EXTERNAL
            extractvalue = pathfinder[KEY_PATHFINDER_VALUE]
            if isexternaltarget:
              target_child = querier.get(pathfinder[KEY_EVALUATOR_LINK])
              target_details = html.fromstring(target_child.content)
            if isexternaltarget or evaluatortarget == TARGET_CURRENT:
              extractmethod = pathfinder[KEY_PATHFINDER_TYPE]
              if extractmethod == PATHFINDER_TYPE_FULLTEXT:
                indexername = pathfinder[KEY_PATHFINDER_INDEXER]
                if not hasattr('', indexername):
                  raise KeyError(indexername)
                extract = target_details.xpath(extractvalue)
                target_pattern = pathfinder[KEY_PATHFINDER_PATTERN]
                target_format = pathfinder[KEY_PATHFINDER_FORMAT]
                if target_format == PATHFINDER_FORMAT_NOW:
                  target = now.strftime(target_pattern)
                  target_items = target.upper().split()
                  target_found = False
                  for line in extract:
                    line = cleanvalue(line)
                    if target_found:
                      if (isexternaltarget and getattr(line, indexername)(name.upper())) or (not isexternaltarget and line != ''):
                        extrainfo = line
                        break
                    else:
                      if line.upper().find(' '.join(target_items)) != -1:
                        target_found = True
                      elif line.upper().find(''.join(target_items)) != -1:
                        target_found = True
                elif target_format == PATHFINDER_FORMAT_LIST:
                  target_found = False
                  extrainfo_line = ''
                  for line in extract:
                    line = cleanvalue(line)
                    if target_found:
                      if (isexternaltarget and getattr(line, indexername)(name.upper())) or (not isexternaltarget and line != ''):
                        extrainfo += '%s: %s\n' % (extrainfo_line, line)
                        target_found = False
                    if test(target_pattern, line):
                      extrainfo_line = line
                      target_found = True
                else:
                  raise KeyError(target_format)
              elif extractmethod == PATHFINDER_TYPE_SHOWCASE:
                extrainfo = cleanvalue(target_details.xpath(extractvalue % name)[0])
              else:
                raise KeyError(extractmethod)
            elif evaluatortarget == TARGET_INDEX:
              extrainfo = cleanvalue(item.xpath(extractvalue)[0])
            else:
              raise KeyError(evaluatortarget)
          except:
            continue
          output.start_item(itemindex)
          output.write_string(scrape_target)
          output.write_int(index)
          output.write_string(name)
          output.write_string(description)
          output.write_string(extrainfo)
          output.write_string(link)

          detailvalues = {}
          for detailname, detail in (config[KEY_DETAILS] if KEY_DETAILS in config else {}).items():
            detailsource = description
            if KEY_DETAILS_SOURCE in detail:
              detailsource = locals()[detail[KEY_DETAILS_SOURCE]]
            truedefault = ''
            writer = output.write_string
            valueconverter = lambda value: value
            detailstype = detail[KEY_DETAILS_TYPE] if KEY_DETAILS_TYPE in detail else TYPE_STRING
            if detailstype == TYPE_INT:
              truedefault = 0
              writer = output.write_int
              valueconverter = int
            elif detailstype == TYPE_FLOAT:
              truedefault = 0.
              writer = output.write_float
              valueconverter = float
            elif detailstype != TYPE_STRING:
              raise KeyError(detailstype)
            value = None
            detailsconversion = detail[KEY_DETAILS_CONVERSION]
            conversionprocess = detailsconversion[KEY_DETAILS_CONVERSION_PROCESS]
            if conversionprocess == CONVERSION_LAYER:
              try: value = calculatelayer(detailsconversion[KEY_DETAILS_CONVERSION_FORMULA], detailvalues)
              except: value = truedefault
            elif conversionprocess == CONVERSION_SCHEDULE:
              try: value = parseschedule(findall(detailsconversion[KEY_DETAILS_CONVERSION_PATTERN], detailsource, IGNORECASE))
              except: value = truedefault
              oldwriter = writer
              writer = lambda values: list(map(oldwriter, values))
            else:
              matchconverter = lambda matches: ','.join(matches) if matches else truedefault
              gotmatch = False
              if conversionprocess == CONVERSION_VALUE:
                matchconverter = lambda matches: valueconverter(matches[0]) if matches else truedefault
              elif conversionprocess == CONVERSION_CALCULATE:
                matchconverter = lambda matches: eval(detailsconversion[KEY_DETAILS_CONVERSION_FORMULA] % tuple(val or truedefault for val in matches)) if matches else truedefault
              else:
                raise KeyError(conversionprocess)
              gotmatch = search(detailsconversion[KEY_DETAILS_CONVERSION_PATTERN], detailsource, IGNORECASE)
              value = valueconverter(detail[KEY_DETAILS_DEFAULT]) if KEY_DETAILS_DEFAULT in detail else truedefault
              if gotmatch:
                try: value = matchconverter(gotmatch.groups())
                except: value = truedefault
            detailvalues[detailname] = value
            writer(value)

          output.end_item()
          index += 1
          itemindex = itemindex + 1

def parseTimevalue(timevalue, daythreshold = None):
  timevalue = timevalue.upper()
  value_separator = ':'
  if timevalue.find(value_separator) == -1:
    value_separator = 'H'
  time_parts = timevalue.split(value_separator)
  if time_parts[-1].find('M') != -1:
    time_period = time_parts[-1][-2:]
    if time_parts[0].find('M') != -1:
      time_parts[0] = time_parts[0][:-2]
    time_hours = int(time_parts[0])
    if time_hours == 0:
      time_hours = 24
    elif time_period == 'AM' and time_hours < 10:
      time_hours += 24
    elif (time_period == 'PM') != (time_hours == 12):
      time_hours += 12
    time_parts[0] = str(time_hours)
    if len(time_parts) > 1:
      if time_parts[-1][:-2] == '':
        time_parts[-1] = '00'
      else:
        time_parts[-1] = time_parts[-1][:-2]
  elif int(time_parts[0]) < 10:
    time_parts[0] = str(int(time_parts[0]) + 12)
  if len(time_parts) == 1:
    time_parts.append('00')
  elif time_parts[-1] == '':
    time_parts[-1] = '00'
  if daythreshold and int(time_parts[0]) < int(daythreshold.split(':')[0]):
    time_parts[0] = str(int(time_parts[0]) + 12)
  time_parts[0] = time_parts[0].zfill(2)
  return ':'.join(time_parts)

def calculatelayer(formula, detailvalues):
  parsedformula = formula
  for name, value in detailvalues.items():
    parsedformula = parsedformula.replace(name, str(value))
  return eval(parsedformula)

def parseschedule(matches):
  start = ''
  end = ''
  if matches:
    start = parseTimevalue(matches[0])
    if len(matches) > 1:
      end = parseTimevalue(matches[1], start)
  return (start, end)

def cleanvalue(value):
  return str(value).strip()

if __name__ == "__main__":
  from confuse import Configuration
  config = Configuration(APPLICATION_NAME)
  config.set_file(APPLICATION_CONFIG_FILENAME)
  execute(config.get())
