#Импортировать нужные библиотеки
from google.colab import files
import numpy as np
import pandas as pd
import plotly.figure_factory as ff
from matplotlib.backends.backend_agg import FigureCanvasAgg
import gspread
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import requests
from urllib.parse import urlencode


#Преобразования входных данных
def timetable_ds_input(input_):
    #Создание источника данных для расписания
    timetable_ds = input_.split('/')
    return GetTimetable(GoogleSpreadsheet(*timetable_ds))

def shortname_ds_input(input_):
    #Создание источника данных для сокращённых названий
    shortname_ds = input_.split('/')
    return GetShortname(GoogleSpreadsheet(*shortname_ds, alternative=True))

def picture_ds_input(input_):
    #Создание источника данных для картинок
    picture_ds = input_.split('/')
    if picture_ds[0] == 'Загрузить вручную':
        return GetPicture(GoogleColabInput())
    return GetPicture(GoogleSpreadsheet(*picture_ds, alternative=True))

def dates_input(input_):
    #Создание списка дат для расписания
    dates = []
    for d in input_:
        if d != '':
            d = d.split('-')
            dates.append(f'{d[2]}.{d[1]}')
    return dates

def tournaments_input(input_):
    #Создание списка турниров для расписания
    all_tournaments = ['Стыки', 'ОПК', 'ЧВ', 'КР', 'МКР', 'ЛП', 'КП', 'ЗЛ']
    tournaments = []
    for i in range(len(input_)):
        if input_[i][0]:
            if input_[i][1]:
                tournaments += list(all_tournaments[i]+np.array(input_[i][1]))
            else:
                tournaments.append(all_tournaments[i])
    return tournaments

def font_ds_input(input_):
    #Создание источника данных для шрифта
    font_ds = input_.split('/')
    return GetFont(GoogleSpreadsheet(*font_ds, alternative=True))

def date_to_str(m):
    #Преобразование даты к виду Х МЕСЯЦА
    months = ['ЯНВАРЯ', 'ФЕВРАЛЯ', 'МАРТА',
              'АПРЕЛЯ', 'МАЯ', 'ИЮНЯ',
              'ИЮЛЯ', 'АВГУСТА', 'СЕНТЯБРЯ',
              'ОКТЯБРЯ', 'НОЯБРЯ', 'ДЕКАБРЯ']
    m = list(map(int, m.split('.')))
    return f'{m[0]} {months[m[1]-1]}'

def weekday_to_str(wd):
    #Преобразование дня недели к виду ДЕНЬ
    weekdays = {'ПН':'ПОНЕДЕЛЬНИК', 'ВТ':'ВТОРНИК', 'СР':'СРЕДА',
                'ЧТ':'ЧЕТВЕРГ', 'ПТ':'ПЯТНИЦА', 'СБ':'СУББОТА', 'ВС':'ВОСКРЕСЕНЬЕ'}
    return weekdays[wd.upper()]

def team_len(st):
    #Длина названия команд
    l = 0
    for s in st:
        l += 1+s.isupper()*0.6
    return round(l+0.6)

def teams_to_str(home, guest, shortname_ds):
    #Создание противостояния команд вида ХОЗЯЕВА — ГОСТИ с длиной, подходящей к таблице
    if team_len(home+guest) > 28:

        home_shortname = shortname_ds.get_shortname(home)
        if home_shortname is None:
            home_shortname = home

        guest_shortname = shortname_ds.get_shortname(guest)
        if guest_shortname is None:
            guest_shortname = guest

        if team_len(home+guest_shortname) <= 28:
            guest = guest_shortname
        elif team_len(home_shortname+guest) <= 28:
            home = home_shortname
        else:
            home = home_shortname
            guest = guest_shortname

    return home+' — '+guest
#Векторизация функции по созданию противостояния
teams_to_str = np.vectorize(teams_to_str, excluded=['shortname_ds'], cache=True)

def tournament_to_str(t, s):
    #Получение полного названия турнира и его стадии
    t = t.split()

    # ОПК, ЧВ, КР, МКР, ЛП, КП, ЗЛ, стыки
    th = t[0].lower().strip()
    if th == 'опк':
        line1 = 'Чемпионат ОПК'
    elif th == 'стыки':
        line1 = 'Стыковые матчи'
    elif th == 'кр':
        line1 = 'Кубок Ректора'
    elif th == 'мкр':
        line1 = 'Малый Кубок Ректора'
    elif th == 'чв':
        line1 = 'Чемпионат выпускников'
    elif th == 'лп':
        line1 = 'Летнее первенство'
    elif th == 'кп':
        line1 = 'Кубок первокурсника'
    elif th == 'зл':
        line1 = 'Зимняя лига'
    else:
        line1 = t[0]

    line2 = ''
    if len(t) == 2:
        if th in ['опк', 'чв', 'лп', 'зл']:
            if t[1].lower().strip() == 'выш':
                line2 = 'Высший дивизион'
            else:
                line2 = f'Дивизион {t[0]}'
        elif th in ['кр', 'мкр', 'кп']:
                line2 = f'Группа {t[1]} '
        elif th == 'стыки':
            if t[1].lower().strip() == 'выш':
                line2 = 'За Высший дивизион'
            elif t[1].strip() == '1':
                line2 = 'За Первый дивизион'
        else:
            line2 = t[1]

    line3 = ''
    if s.lower().strip() == 'ф':
        line3 = 'Финал'
    elif s.lower().strip() == '3 м':
        line3 = 'Матч за третье место'
    elif '/' in s:
        line3 = f'{s} финала'
    elif s.isdigit():
        line3 = f'{s} тур'
    else:
        line3 = s

    if not line2:
        line2 = line3
        line3 = ''
    
    return (line1, line2, line3)

def background_to_str(b, t):
    #Получение названия обложки из типа обложки и названия турнира
    b = b.split()
    if type(t) == str:
      t = [t]
    t = set(map(str.strip, map(str.lower, t)))
    tournaments = []
    if any('кр' in tt for tt in t):
        tournaments += ['КР']
    if  any('опк' in tt for tt in t) or any('стыки' in tt for tt in t):
        tournaments += ['ОПК']
    if any('чв' in tt for tt in t):
        tournaments += ['ЧВ']
    if any('лп' in tt for tt in t):
        tournaments += ['ЛП']
    if any('кп' in tt for tt in t):
        tournaments += ['КП']
    if any('зл' in tt for tt in t):
        tournaments += ['ЗЛ']
    return f'{b[0]} {"+".join(tournaments)} {" ".join(b[1:])}'.strip()

def yadisk_to_url(url):
    #Получение ссылки для загрузки с Я.Диска
    base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?'
    final_url = base_url + urlencode(dict(public_key=url))
    response = requests.get(final_url)
    return response.json()['href']

def download_file(url):
    #Загрузка файла
    if 'yandex' in url.lower():
        url = yadisk_to_url(url)
    return requests.get(url).content

def make_timetable_picture(background_ds, background, timetable_ds, dates, tournaments, shortname_ds):
    #Создание окончательной картинки с расписанием
    background_ = background_to_str(background, tournaments)
    timetable_picture = background_ds.get_picture(background_).resize((1280, 1280))
    tournaments_high = []
    tournaments_without_high = []
    for t in tournaments:
        t = t.lower().strip()
        if 'выш' in t:
            tournaments_high.append(t)
        else:
            tournaments_without_high.append(t)
    offset = 0
    for date in dates:
        timetable = timetable_ds.get_timetable(date)
        #if timetable.shape[0] == 0:
        #   pass
        timetable = timetable[((timetable['див'].str.lower().str.strip().str.contains('|'.join(tournaments_without_high)) == True) &
                               (timetable['див'].str.lower().str.strip().str.contains('выш') == False) |
                               (timetable['див'].str.lower().str.strip().isin(tournaments_high))) &
                              #(timetable['див'].str.lower().str.strip().str.contains('резерв') == False) &
                              (timetable['счет'].str.lower().str.strip().str.contains('перенос') == False) &
                              (timetable['счет'].str.lower().str.strip().str.contains('тп') == False)].reset_index(drop=True).copy()

        date = date_to_str(date)
        weekday = timetable.loc[0, 'дн']
        weekday = weekday_to_str(weekday)
        time = timetable.loc[:, 'время']
        stadium = timetable.loc[:, 'поле']
        tournament = timetable.loc[:, 'див']
        teams = teams_to_str(timetable.loc[:, 'команда 1'].str.strip(), timetable.loc[:, 'команда 2'].str.strip(), shortname_ds)
        timetable = pd.DataFrame(columns=[f'{date} // {weekday}', ''])
        timetable.iloc[:, 0] = time+' // '+teams
        timetable.iloc[:, 1] = tournament+' // '+stadium

        colorscale = [[0, '#620931'],[.5, '#ffffff'],[1, '#d9e3db']]
        fig = ff.create_table(
            timetable,
            index=False,
            colorscale=colorscale,
            height_constant=60,
        )
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 37
        fig.update_layout(
            width=1440,
            height=60*(1+timetable.shape[0])
        )
        fig_bytes = fig.to_image(format="png")
        buf = BytesIO(fig_bytes)

        timetable = Image.open(buf)
        timetable = timetable.crop((22, 0, 1082, timetable.size[1]))
        timetable_picture.paste(timetable, (110, 290+offset))
        offset += timetable.size[1]+60

    return timetable_picture

def make_cover(background_ds, background, logo_ds, font_ds, font, team_1, team_2, date, tournament):
    #Создание обложки для видео
    cover = background_ds.get_picture(background).resize((1280, 720))
    big_font = font_ds.get_font(font, size=40)
    small_font = font_ds.get_font(font, size=30)
    logo_1 = logo_ds.get_picture(team_1).resize((240, 240))
    logo_2 = logo_ds.get_picture(team_2).resize((240, 240))

    mask = Image.new('L', (240, 240), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((5, 5, 235, 235), fill=255)

    draw = ImageDraw.Draw(cover)

    draw.ellipse((190, 200, 190+260, 200+260), fill='white') 
    cover.paste(logo_1, (190+10, 200+10), mask)
    draw.text(
        (190+260//2-round(big_font.getlength(team_1)/2), 200+260+20),
        team_1,
        font=big_font,
        fill='white')

    draw.ellipse((830, 200, 830+260, 200+260), fill='white') 
    cover.paste(logo_2, (830+10, 200+10), mask)
    draw.text(
        (830+260//2-round(big_font.getlength(team_2)/2), 200+260+20),
        team_2,
        font=big_font,
        fill='white')

    draw.text(
        (640-round(small_font.getlength(date)/2), 130 + 0*(30+5)),
        date,
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(tournament[0])/2), 130 + 1*(30+5)),
        tournament[0],
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(tournament[1])/2), 130 + 2*(30+5)),
        tournament[1],
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(tournament[2])/2), 130 + 3*(30+5)),
        tournament[2],
        font=small_font,
        fill='white')

    return cover

def make_many_covers(background_ds, background, logo_ds, font_ds, font, timetable_ds, dates):
    #Создание обложек из расписания с матчами
    covers = []
    for date in dates:
        timetable = timetable_ds.get_timetable(date)
        timetable = timetable[(timetable['видео'].isna() == False) &
                              (timetable['видео'] != '')].reset_index(drop=True).copy()

        date = date_to_str(date).lower()
        for i in timetable.index:
            background_ = background_to_str(background, timetable.loc[i, 'див'])
            team_1 = timetable.loc[i, 'команда 1'].strip()
            team_2 = timetable.loc[i, 'команда 2'].strip()
            date_ = f'{date} {timetable.loc[i, "время"]}'
            tournament = tournament_to_str(timetable.loc[i, 'див'], timetable.loc[i, 'тур'])
            covers.append(make_cover(background_ds, background_, logo_ds, font_ds, font, team_1, team_2, date_, tournament))

    return covers


class GoogleAccount(object):
    #Класс синглтон для установления связи с google-api
    __instance = None
    __key = 'key.json'
    __ga = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls.__ga = gspread.service_account(filename=cls.__key)
        return cls.__instance
    
    def __call__(self):
        return self.__ga


class DataSource(object):
    #Класс-родитель для источников данных
    def get_timetable(self):
        print('Из этого источника данных невозможно получить расписание')
    
    def get_picture(self):
        print('Из этого источника данных невозможно получить картинку')
    
    def get_tournament_table(self):
        print('Из этого источника данных невозможно получить турнирную таблицу')
    
    def get_shortname(self):
        print('Из этого источника данных невозможно получить сокращённое название команды')

    def get_font(self):
        print('Из этого источника данных невозможно получить почерк')


class GetTimetable(DataSource):
    #Класс для получения расписания из источника данных
    __ds = None
    __cache = {}
    def __init__(self, ds):
        self.__ds = ds
    
    def get_timetable(self, date):
        if date not in self.__cache:
            self.__cache[date] = self.__ds.get_timetable(date)
        return self.__cache[date]


class GetPicture(DataSource):
    #Класс для получения картинки из источника данных
    __ds = None
    __cache = {}
    def __init__(self, ds):
        self.__ds = ds
    
    def get_picture(self, key):
        if key not in self.__cache:
            self.__cache[key] = self.__ds.get_picture(key)
        return self.__cache[key]

class GetFont(DataSource):
    #Класс для получения почерка из источника данных
    __ds = None
    __cache = {}
    def __init__(self, ds):
        self.__ds = ds
    
    def get_font(self, key, size):
        if (key, size) not in self.__cache:
            self.__cache[(key, size)] = self.__ds.get_font(key, size)
        return self.__cache[(key, size)]

class GetShortname(DataSource):
    #Класс для получения сокращённого названия из источника данных
    __ds = None
    __cache = {}
    def __init__(self, ds):
        self.__ds = ds
    
    def get_shortname(self, team):
        if team not in self.__cache:
            self.__cache[team] = self.__ds.get_shortname(team)
        return self.__cache[team]


class GetTournamentTable(DataSource):
    #Класс для получения турнирной таблицы из источника данных
    __ds = None
    def __init__(self, ds):
        self.__ds = ds
    
    def get_tournament_table(self, args):
        return self.__ds.get_tournament_table(args)


class GoogleSpreadsheet(DataSource):
    #Класс для источника данных - google spreadsheet
    __ds = None
    __alternative = False
    def __init__(self, spreadsheet_name, worksheet_name, alternative=False):
        ga = GoogleAccount()
        self.__ds = ga().open(spreadsheet_name).worksheet(worksheet_name)
        self.__alternative = alternative

    def get_timetable(self, date):

        worksheet = self.__ds
        timetable = None
        try:
            cell_list = worksheet.findall(date.strip().lower())
            cell_list = list(map(lambda c: c.row, cell_list))
            timetable = []
            for cl in cell_list:
                timetable.append(worksheet.row_values(cl))
            columns = worksheet.row_values(1)
            timetable = pd.DataFrame(timetable)
            cols = timetable.shape[1]
            if cols < len(columns):
                columns = columns[:cols]
            else:
                columns += [''] * (cols-len(columns))
            timetable.columns = list(map(str.lower, map(str.strip, columns)))
        except:
            if self.__alternative:
                pass
        return timetable

    def get_picture(self, key):

        worksheet = self.__ds
        picture = None
        try:
            cell = worksheet.find(key.strip().lower())
            url = worksheet.cell(cell.row, cell.col+1).value
            buf = BytesIO(download_file(url))       
            picture = Image.open(buf)
        except:
            if self.__alternative:
                alternative_ds = GetPicture(GoogleColabInput())
                picture = alternative_ds.get_picture(key)
        return picture
    
    def get_shortname(self, team):

        if team_len(team) <= 14:
            return team

        worksheet = self.__ds
        shortname = None
        try:
            cell = worksheet.find(team.strip().lower())
            shortname = worksheet.cell(cell.row, cell.col+1).value
        except:
            if self.__alternative:
                alternative_ds = GetShortname(GoogleColabInput())
                shortname = alternative_ds.get_shortname(team)
            else:
                shortname = team
        return shortname

    def get_font(self, key, size):

        worksheet = self.__ds
        font = None
        try:
            cell = worksheet.find(key.strip().lower())
            url = worksheet.cell(cell.row, cell.col+1).value
            buf = BytesIO(download_file(url))
            font = ImageFont.truetype(buf, size=size)
        except:
            if self.__alternative:
                alternative_ds = GetFont(GoogleColabInput())
                font = alternative_ds.get_font(key, size)
        return font

        
class GoogleColabInput(DataSource):
    #Класс для источника данных - ввод в google colab
    def get_picture(self, key):
        if key == '':
            print(f'↓ Загрузи картинку')
        else:
            print(f'↓ Загрузи картинку "{key}" вручную, т.к. её нет в базе данных')
        picture = files.upload()
        buf = BytesIO(picture[list(picture.keys())[0]])
        return Image.open(buf)

    def get_font(self, key, size):
        worksheet = self.__ds
        if key == '':
            print(f'↓ Загрузи шрифт')
        else:
            print(f'↓ Загрузи шрифт "{key}" вручную, т.к. его нет в базе данных')
        font = files.upload()
        buf = BytesIO(font[list(font.keys())[0]])
        return ImageFont.truetype(buf, size=size)

    def get_shortname(self, team):
        return input(f'Введите сокращенное название для команды "{team}"\n')
