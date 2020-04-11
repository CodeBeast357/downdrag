from re import search, match as test, findall, IGNORECASE
from lxml import html
from datetime import datetime
from urllib.parse import urljoin
from abc import ABC, abstractmethod
from querier import DataQuerier
from outputs import ResultsWriter

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
KEY_OUTPUTS = 'outputs'
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

def execute(config):
  now = datetime.now()
  profiles = config[KEY_PROFILES]
  querierconfig = config[KEY_QUERIER] if KEY_QUERIER in config else {}
  with DataQuerier.Create(querierconfig) as querier:
    headers = MAIN_FIELDS.copy()
    for detailname, detail in config[KEY_DETAILS].items():
      conversionprocess = detail[KEY_DETAILS_CONVERSION][KEY_DETAILS_CONVERSION_PROCESS]
      if conversionprocess in USAGE_TYPES_MULTIPART:
        for headerformat in USAGE_TYPES_MULTIPART[conversionprocess]:
          headers.append(headerformat % detailname)
      else:
        headers.append(detailname)

    with ResultsWriter.Create(config[KEY_OUTPUTS], headers) as output:
      itemindex = 0
      for scrape_target, scrape_profile in profiles.items():
        pathfinder = scrape_profile[KEY_PATHFINDER]
        for page in querier.pages(scrape_profile):
          data = page.xpath(scrape_profile[KEY_ITEMS])
          index = 0
          for item in data:
            if item is None: continue
            try:
              linkinfos = scrape_profile[KEY_INFOS] if KEY_INFOS in scrape_profile else 'descendant::a'
              link = str(item.xpath(linkinfos)[0].attrib['href'])
              infos = page.get(link)
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
                target_details = page.get(pathfinder[KEY_EVALUATOR_LINK])
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
