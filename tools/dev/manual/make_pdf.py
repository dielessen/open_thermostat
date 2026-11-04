"""OpenThermostat installation manual (Dutch) as a PDF.

Usage: make_pdf.py [--fonts DIR] <output.pdf>

Needs reportlab (see README.md). The PDF is generated output: write it to out/, do not commit it.

Two things change with a release: the versions just below and the names of the Home Assistant menus.
Every name that Home Assistant shows is written through ui() or named(), so that
tools/dev/test_manual_labels.py can check it against the Dutch texts of the integration.
"""
import argparse
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# ---- What the manual is written for (change these at each release) ------------------------------------
# The release pair: E32 firmware rc.5 goes with Home Assistant integration 1.0.0rc6 (see tools/dev/prepare_rc5.py).
E32_TAG = "v1.0.0-e32v2-rc.5"
E32_VERSION = "1.0.0-rc.5"
HA_VERSION = "1.0.0rc6"

# ---- Fonts ---------------------------------------------------------------------------------------------
# The first complete set wins: Arial and Consolas from Windows (also reachable from WSL), then DejaVu.
FONT_DIRS = ["/mnt/c/Windows/Fonts", "C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts",
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"]
FONT_SETS = [
    {"Sans": "arial.ttf", "Sans-Bold": "arialbd.ttf", "Sans-Italic": "ariali.ttf", "Mono": "consola.ttf"},
    {"Sans": "DejaVuSans.ttf", "Sans-Bold": "DejaVuSans-Bold.ttf", "Sans-Italic": "DejaVuSans-Oblique.ttf",
     "Mono": "DejaVuSansMono.ttf"},
]


def register_fonts(extra_dir=None):
    """Register the first font set found in the given folder or the usual places; return its file names."""
    folders = [Path(d) for d in ([extra_dir] if extra_dir else []) + FONT_DIRS]
    for names in FONT_SETS:
        for folder in folders:
            if all((folder / file).is_file() for file in names.values()):
                for name, file in names.items():
                    pdfmetrics.registerFont(TTFont(name, str(folder / file)))
                pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Italic",
                                              boldItalic="Sans-Bold")
                return names
    sys.exit("No usable fonts found. Looked for Arial/Consolas or DejaVu in: " + ", ".join(map(str, folders))
             + ". Pass the folder with --fonts DIR.")


# ---- Look ----------------------------------------------------------------------------------------------
INK = colors.HexColor("#1f2933"); MUTED = colors.HexColor("#52606d"); ACCENT = colors.HexColor("#0f766e")
LINK = "#0b6bcb"; TIP_BG = colors.HexColor("#e6f4f1"); WARN_BG = colors.HexColor("#fdf3e1"); WARN = colors.HexColor("#b45309")
LINE = colors.HexColor("#d9e2ec")

S = {
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=26, leading=31, textColor=INK, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="Sans", fontSize=13, leading=18, textColor=MUTED, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=21, textColor=ACCENT, spaceBefore=10, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12.5, leading=16, textColor=INK, spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName="Sans", fontSize=10.5, leading=14.5, textColor=INK, spaceAfter=5, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Sans", fontSize=9, leading=12, textColor=MUTED, spaceAfter=4),
    "step": ParagraphStyle("step", fontName="Sans", fontSize=10.5, leading=14.5, textColor=INK),
    "num": ParagraphStyle("num", fontName="Sans-Bold", fontSize=11, leading=14.5, textColor=colors.white, alignment=1),
    "box": ParagraphStyle("box", fontName="Sans", fontSize=10, leading=13.5, textColor=INK),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.6, leading=11.5, textColor=INK),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=9.5, leading=12.5, textColor=INK),
}
W = A4[0] - 36 * mm
SEEN = []  # every text given to a Paragraph, to check afterwards that the fonts have all its characters


def a(url, text=None):
    return f'<link href="{url}" color="{LINK}"><u>{text or url}</u></link>'


def p(text, style="p"):
    SEEN.append(text)
    return Paragraph(text, S[style])


def ui(*labels):
    """Names as Home Assistant shows them (the Dutch translation), in bold; several make a menu path."""
    return " → ".join(f"<b>{label}</b>" for label in labels)


def named(*labels):
    """A list of such names: "A, B en C"."""
    bold = [f"<b>{label}</b>" for label in labels]
    return ", ".join(bold[:-1]) + " en " + bold[-1] if len(bold) > 1 else bold[0]


def steps(items, start=1):
    rows = []
    for i, text in enumerate(items, start):
        rows.append([p(str(i), "num"), p(text, "step")])
    t = Table(rows, colWidths=[8 * mm, W - 10 * mm], hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
             ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    for r in range(len(rows)):
        style.append(("BACKGROUND", (0, r), (0, r), ACCENT))
    t.setStyle(TableStyle(style))
    return t


def box(title, text, kind="tip"):
    bg, edge = (TIP_BG, ACCENT) if kind == "tip" else (WARN_BG, WARN)
    t = Table([[p(f"<b>{title}</b><br/>{text}", "box")]], colWidths=[W], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 6)])


def table(rows, widths):
    data = [[p(f"<b>{c}</b>" if n == 0 else c, "cell") for c in r] for n, r in enumerate(rows)]
    t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
                           ("FONTNAME", (0, 0), (-1, 0), "Sans-Bold"), ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


REL = "https://github.com/dielessen/open_thermostat/releases"
DOCS = "https://github.com/dielessen/open_thermostat/blob/main/docs/"


def content():
    story = []
    add = story.extend

    # ---- Cover -----------------------------------------------------------------------------------------
    add([Spacer(1, 30 * mm), p("OpenThermostat", "title"),
         p("Handleiding: van BBQKees-gateway naar slimme thermostaat", "sub"),
         p("Flashen van de BBQKees Gateway E32 V2, de Home Assistant-integratie installeren en de E32 in gebruik "
           "nemen als thermostaat, met de keteltest en de overname van de ketel."),
         Spacer(1, 6),
         table([["Hoort bij", "Versie"],
                ["E32-firmware", f"{E32_TAG} (of nieuwer)"],
                ["Home Assistant-integratie", f"{HA_VERSION} (of nieuwer)"],
                ["Home Assistant", "2026.10.0 of nieuwer"]], [60 * mm, W - 60 * mm]),
         Spacer(1, 8),
         box("Zo gebruik je deze handleiding",
             "Werk de hoofdstukken op volgorde af en vink af wat klaar is. Blauwe onderstreepte tekst is een link: "
             "klik erop in de PDF. Knoppen staan hier met hun naam zoals de E32 en Home Assistant ze tonen. "
             "Met een Nederlandse browser zie je op de E32 de Nederlandse namen (Overzicht, Ruimtes, Huis, Ketel, Systeem). "
             "Met Home Assistant in het Nederlands zie je de Nederlandse namen van de integratie. Staat een van beide "
             "in een andere taal, dan zijn de namen anders."),
         box("Belangrijk vooraf",
             "• De E32 stuurt <b>niets</b> naar je ketel tot jij de overname bevestigt (hoofdstuk 9).<br/>"
             "• Het flashen <b>wist</b> de oorspronkelijke EMS-ESP-software op de gateway.<br/>"
             "• Werk aan de ketelaansluiting alleen met de ketel <b>uit</b>. Twijfel je? Vraag een installateur.",
             "warn"),
         p("Tijd: ongeveer een uur voor de E32 en een half uur voor Home Assistant, plus een half uur voor de keteltest.", "small"),
         PageBreak()])

    # ---- 1 What you need -------------------------------------------------------------------------------
    add([p("1. Wat heb je nodig", "h1"),
         table([["Wat", "Toelichting"],
                ["BBQKees Gateway <b>E32 V2</b>", "ESP32 met 16 MB geheugen. De oude E32 en de S3-gateways zijn andere borden. "
                 + a("https://bbqkees-electronics.nl/", "bbqkees-electronics.nl")],
                ["Ketel met <b>EMS Classic</b> (EMS 1.0)", "Direct of via een adapter zoals de Bosch EasyControl Adapter. "
                 "Ketels die alleen EMS+ spreken worden nog niet ondersteund (gepland voor 1.1)."],
                ["USB-C-kabel <b>met data</b>", "Geen oplaadkabeltje: een datakabel. Plus een computer met Chrome of Edge."],
                ["Wifi 2,4 GHz", "De E32 werkt niet op 5 GHz. Een netwerkkabel kan ook."],
                ["Home Assistant", "Versie 2026.10.0 of nieuwer, met internet."],
                ["MQTT-broker", "Bijvoorbeeld de Mosquitto-add-on in Home Assistant (hoofdstuk 5)."],
                ["HACS", "De Home Assistant Community Store, om de integratie te installeren. "
                 + a("https://hacs.xyz/docs/use/", "HACS installeren")],
                ["Per kamer een temperatuurbron", "Een Bluetooth-thermometer, of een sensor of thermostaat die al in Home Assistant zit."]],
               [55 * mm, W - 55 * mm]),
         Spacer(1, 4),
         p("<b>Niet nodig:</b> een cloud-account, de ESPHome-integratie of een bestaande thermostaat. "
           "Heb je wel een thermostaat (bijvoorbeeld een tado) op de ketel, dan houdt die de ketel in handen tot jij overstapt."),
         ])

    # ---- 2 Flash ---------------------------------------------------------------------------------------
    add([p("2. De firmware op de gateway zetten (eenmalig, via USB)", "h1"),
         p("Dit doe je maar één keer. Latere updates gaan via het netwerk en houden je instellingen."),
         box("Wil je ooit terug naar EMS-ESP?",
             "Maak dan eerst een volledige back-up en exporteer je EMS-ESP-instellingen, zoals beschreven in "
             + a(DOCS + "FLASHING.md#make-a-full-backup-first", "USB-back-up en herstel") + ".", "warn"),
         p("2.1 Firmware downloaden", "h2"),
         steps([f"Open de {a(REL, 'releasepagina')} en kies de nieuwste release waarvan de naam begint met "
                f"<b>v</b> en <b>e32v2</b> bevat, bijvoorbeeld <font name='Mono'>{E32_TAG}</font>.",
                "Download onder <b>Assets</b> het bestand <font name='Mono'>open-thermostat-e32v2-&lt;versie&gt;.zip</font>. "
                "Niet de \"Source code\"-downloads.",
                "Pak de ZIP uit in een nieuwe map. Je hebt twee bestanden nodig: <font name='Mono'>e32v2-factory.bin</font> "
                "(de installatie) en <font name='Mono'>FACTORY-CHECK.txt</font> (de controlecijfers)."]),
         p("2.2 Gateway aan de computer", "h2"),
         steps(["Haal de gateway los van de ketel (EMS-kabel) en van elke andere voeding.",
                "Sluit de USB-C-poort van de gateway aan op je computer. De gateway krijgt stroom via USB.",
                "Ziet je computer geen nieuwe COM-poort? Installeer dan de USB-driver die BBQKees aanraadt: "
                + a("https://bbqkees-electronics.nl/wiki/gateway/firmware-update-and-downgrade.html#gateway-s3-s3-lr-and-e32-v2",
                    "BBQKees firmware-update-handleiding") + "."]),
         p("2.3 Flashen in de browser met ESPConnect", "h2"),
         p(a("https://thelastoutpostworkshop.github.io/ESPConnect/", "ESPConnect") +
           " is een gratis flashprogramma dat in <b>Chrome of Edge</b> draait (niet in Safari of Firefox). "
           "Je hoeft niets te installeren."),
         steps(["Open ESPConnect, kies <b>115200</b> baud als daarom gevraagd wordt, klik <b>Connect</b> en kies de poort van de gateway.",
                "Controleer <b>Device Info</b>: daar moet <b>ESP32</b> (niet ESP32-S3) met <b>16 MB</b> flash staan. Zo niet: stop, dit is geen E32 V2.",
                "Ga naar <b>Flash Tools → Flash Firmware</b> en kies <font name='Mono'>e32v2-factory.bin</font>.",
                "Zet de <b>flash offset</b> op precies <font name='Mono'>0x0</font> en vink <b>Erase entire flash before writing</b> aan.",
                "Klik <b>Flash Firmware</b>, controleer bestandsnaam en <font name='Mono'>0x0</font>, en wacht tot er \"success\" staat. Laat de kabel zitten.",
                "Controleer het resultaat <b>vóór de eerste herstart</b>: <b>Flash Tools → Flash Integrity</b>, start "
                "<font name='Mono'>0x0</font>, lengte = de <b>Length</b> uit FACTORY-CHECK.txt. Klik <b>Compute MD5</b>. "
                "De uitkomst moet gelijk zijn aan \"MD5 before first boot\" in FACTORY-CHECK.txt. Anders: opnieuw flashen.",
                "Klik <b>Disconnect</b>, trek de USB-kabel eruit en steek hem er weer in. De gateway start nu OpenThermostat."]),
         box("Liever via de opdrachtregel?",
             "Dat kan met esptool; de exacte commando's staan in de " + a(DOCS + "INSTALL.md#24-route-b-on-the-command-line-with-esptool", "installatiegids, route B") + ". "
             "Lukt verbinden niet: probeer een andere datakabel, sluit direct op de computer aan (geen hub) en sluit andere programma's die de poort gebruiken."),
         ])

    # ---- 3 Wi-Fi + password + basics -------------------------------------------------------------------
    add([p("3. Eerste start: wifi, wachtwoord en basisinstellingen", "h1"),
         p("3.1 Wifi", "h2"),
         steps(["Na een paar seconden verschijnt een wifinetwerk <b>OpenThermostat-xxxxxx</b>. Het wachtwoord is "
                "<font name='Mono'>openthermostat</font>.",
                "Verbind je telefoon of laptop ermee. De pagina <b>Connect to your WiFi</b> opent meestal vanzelf; anders "
                "ga je naar <font name='Mono'>http://10.10.10.1/</font>. Vraagt je telefoon of hij op een netwerk zonder internet mag blijven: ja.",
                "Kies <b>Find networks</b>, kies je thuisnetwerk (alleen 2,4 GHz wordt getoond), vul het wachtwoord in en kies <b>Connect</b>.",
                "Lukt het, dan toont de pagina het nieuwe adres van de E32 op je thuisnetwerk, bijvoorbeeld "
                "<font name='Mono'>http://192.168.1.50</font>. <b>Schrijf dit op of maak een bladwijzer</b>: je hebt het nodig voor Home Assistant."]),
         p("Het setup-netwerk blijft ongeveer 15 minuten open. Te laat? Stroom eraf en erop, dan opent het opnieuw. "
           "De E32 is vaak ook bereikbaar als <font name='Mono'>http://openthermostat-xxxxxx.local/</font>.", "small"),
         p("3.2 Eigen wachtwoord", "h2"),
         steps(["Open het adres van de E32 en log in met gebruiker <font name='Mono'>admin</font> en wachtwoord <font name='Mono'>admin</font>.",
                "De E32 vraagt meteen om <b>Choose your own password</b>: kies een wachtwoord van 8 tot 64 tekens en sla het op.",
                "Schrijf het wachtwoord op. Home Assistant vraagt er later om. Tot je het verandert, accepteert de E32 geen enkele wijziging."]),
         p("3.3 Tijdzone en ketelontvangst", "h2"),
         p("Beide staan op <b>Systeem → Network and Home Assistant</b>. Kies onderaan <b>Save settings</b> en laat de E32 herstarten."),
         steps(["<b>Time</b>: kies je tijdzone (Europe/Amsterdam) of klik <b>Use this time zone</b>. De weekprogramma's volgen deze klok.",
                "<b>Advanced settings → Hardware services</b>: vink <b>Boiler bus (EMS) on</b> aan. Daarmee <i>luistert</i> de E32 naar de ketel; "
                "hij stuurt nog niets."]),
         ])

    # ---- 4 Boiler --------------------------------------------------------------------------------------
    add([p("4. De gateway op de ketel aansluiten", "h1"),
         box("Veiligheid eerst",
             "Zet de ketel <b>uit</b> en haal de stekker eruit voordat je iets op de EMS-bus aansluit of loskoppelt. Volg de "
             "aanwijzingen van BBQKees voor jouw ketel: " + a("https://bbqkees-electronics.nl/wiki/", "BBQKees wiki") + " en "
             + a("https://bbqkees-electronics.nl/wiki/gateway/hardware-details.html", "hardwaredetails van de gateway") + ".", "warn"),
         steps(["Sluit de gateway aan op de EMS-bus van de ketel en voed hem zoals BBQKees voor jouw situatie beschrijft.",
                "Heb je een bestaande thermostaat op de ketel? <b>Laat die voorlopig aangesloten.</b> De keteltest zegt wanneer hij eraf mag. "
                "Geen thermostaat? Ook goed: die is niet nodig.",
                "Zet de ketel weer aan.",
                "Open op de E32 de pagina <b>Ketel</b>. Binnen een paar minuten zie je echte waarden: aanvoer- en retourtemperatuur, "
                "branderstatus en de displaycode in woorden.",
                "Kies onder <b>Boiler model</b> jouw ketel en sla op. Dit verandert alleen de naam en het plaatje."]),
         p("Niet elke ketel meldt alles (waterdruk ontbreekt bijvoorbeeld vaak). De E32 verzint nooit een waarde.", "small"),
         p("Optioneel: Bluetooth-thermometers", "h2"),
         p("Een Bluetooth-thermometer ontvangt de E32 zelf, dus die werkt ook als Home Assistant uit staat. Ondersteund: "
           "Shelly BLU H&amp;T Display, Xiaomi Monitor 3 (met bindkey) en thermometers met pvvx-firmware."),
         steps(["Open <b>Systeem → Bluetooth sensors</b> en kies <b>Search nearby</b>.",
                "Klik je sensor, geef hem een duidelijke naam (\"Thermometer woonkamer\") en vul alleen een sleutel in als de sensor die gebruikt.",
                "Kies <b>Save Bluetooth settings</b>. De E32 herstart na zo'n 30 seconden; daarna staat de temperatuur onder <b>Your sensors</b>."]),
         ])

    # ---- 5 MQTT ----------------------------------------------------------------------------------------
    add([p("5. MQTT: de verbinding tussen E32 en Home Assistant", "h1"),
         p("MQTT is de postbode tussen de E32 en Home Assistant. Heb je al een MQTT-broker in Home Assistant, sla 5.1 dan over."),
         p("5.1 Broker en MQTT-integratie", "h2"),
         steps(["Home Assistant: <b>Instellingen → Add-ons → Add-on store</b>, installeer de <b>Mosquitto broker</b> en start hem. "
                + a("https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md", "Uitleg Mosquitto"),
                "Home Assistant biedt daarna de integratie <b>MQTT</b> aan onder <b>Instellingen → Apparaten en diensten</b>. Voeg die toe. "
                + a("https://www.home-assistant.io/integrations/mqtt/", "Uitleg MQTT-integratie")]),
         p("5.2 Een login voor de E32", "h2"),
         steps(["Maak in Home Assistant een aparte gebruiker, bijvoorbeeld <font name='Mono'>e32</font>: "
                "<b>Instellingen → Personen → Gebruikers → Gebruiker toevoegen</b>. (Het tabblad Gebruikers zie je als "
                "<b>Geavanceerde modus</b> aan staat in je profiel.) Geen beheerder nodig."]),
         p("5.3 MQTT op de E32", "h2"),
         p("Op de E32: <b>Systeem → Network and Home Assistant</b>, onderdeel <b>MQTT</b>:"),
         steps(["Vink <b>Enabled</b> aan en laat <b>Publish Home Assistant MQTT Discovery</b> aangevinkt.",
                "<b>Broker address</b>: het adres van je Home Assistant, bijvoorbeeld <font name='Mono'>192.168.1.10</font>. "
                "<b>Broker port</b>: <font name='Mono'>1883</font>.",
                "<b>User name</b> en <b>Password</b>: de login uit 5.2.",
                "Laat <b>Advanced</b> en het onderdeel <b>Home Assistant</b> zoals ze zijn. Kies <b>Save settings</b> en laat de E32 herstarten."]),
         ])

    # ---- 6 and 7 HA integration ------------------------------------------------------------------------
    add([p("6. De Home Assistant-integratie installeren (HACS)", "h1"),
         steps(["Open <b>HACS</b>, de drie puntjes rechtsboven, en kies <b>Custom repositories</b>.",
                "Vul in: <font name='Mono'>https://github.com/dielessen/openthermostat-ha</font>, type <b>Integration</b>, en kies <b>Add</b>. "
                "(" + a("https://github.com/dielessen/openthermostat-ha", "de repository") + ")",
                "Zoek in HACS naar <b>OpenThermostat</b>, open hem en kies <b>Download</b>.",
                f"Kies de versie die bij je firmware hoort. Is de nieuwste een <i>pre-release</i> (zoals <font name='Mono'>{HA_VERSION}</font>), "
                "open dan <b>Need a different version?</b> en kies die versie.",
                "Herstart Home Assistant: <b>Instellingen → Systeem → Herstarten</b>."]),
         box("Tip: pre-releases als update krijgen",
             "Zolang er alleen pre-releases zijn: ga naar <b>Instellingen → Apparaten en diensten → HACS</b>, open het apparaat "
             "<b>OpenThermostat</b>, schakel de entiteit <b>Pre-release</b> in en zet hem aan. Anders biedt HACS een "
             "\"update\" met een vreemde code (bijvoorbeeld 5043af7) aan; die kun je overslaan."),
         p("7. Integratie toevoegen en de E32 koppelen", "h1"),
         steps(["<b>Instellingen → Apparaten en diensten → Integratie toevoegen</b>, kies <b>OpenThermostat</b>.",
                "Het formulier " + ui("Verwarmingsinstallatie instellen") + " opent. Geef de installatie een naam (\"Thuis\"), "
                "laat " + ui("OpenThermostat-dashboard tonen") + " aangevinkt en kies " + ui("Installatie toevoegen") + ".",
                "Open bij OpenThermostat <b>Configureren</b> (het tandwiel). Configureren heeft zes onderdelen: "
                + named("Ruimtes", "Huis", "Verwarming en ketel", "Energie en buitentemperatuur", "E32-verbinding",
                        "Geavanceerd en diagnose") + ". Elk submenu heeft " + ui("← Terug") + "; " + ui("Klaar")
                + " sluit Configureren.",
                "Kies " + ui("E32-verbinding") + ".",
                "Vul bij " + ui("Webadres van de E32") + " het adres in, mét <font name='Mono'>http://</font> (uit 3.1), en bij "
                + ui("E32-wachtwoord") + " het E32-wachtwoord (uit 3.2). Kies <b>Verzenden</b>.",
                "Home Assistant controleert alles en wacht op het eerste bericht van de E32. Dit kan tot twee minuten duren; de E32 kan één keer herstarten.",
                "Verschijnt " + ui("E32 verbonden") + ", ga dan door met " + ui("Eerste ruimte toevoegen")
                + ". Op de E32 staat nu <b>Home Assistant: connected</b>."]),
         ])

    # ---- 8 Rooms ---------------------------------------------------------------------------------------
    add([p("8. Je kamers instellen", "h1"),
         p("Elke kamer heeft een of meer temperatuurbronnen, een weekprogramma en eventueel radiatorkranen of een instelapparaat."),
         steps(["Kies " + ui("Eerste ruimte toevoegen") + " (later: <b>Configureren</b> → " + ui("Ruimtes", "Ruimte toevoegen") + ").",
                "Vul bij " + ui("Naam van de ruimte") + " de naam in, zet " + ui("Verwarmen") + " op " + ui("Aan")
                + " en kies bij " + ui("Verwarmingstype") + " " + ui("Radiatoren") + " of " + ui("Vloerverwarming") + ".",
                "Kies de temperatuurbronnen: " + ui("Temperatuurbronnen uit Home Assistant") + " (sensoren of thermostaten) en/of "
                + ui("Bluetooth-sensoren op de E32") + ".",
                "Laat " + ui("Weekprogramma op de E32") + " voorlopig op de standaard staan; je past het straks makkelijk aan "
                "op het tabblad " + ui("Weekprogramma") + " van het dashboard.",
                "Optioneel, in de ingeklapte onderdelen: " + ui("Ramen en deuren") + " (pauzeert de kamer als er iets open staat), "
                + ui("Personen") + " van de kamer met een eigen afwezigheidstemperatuur, en de " + ui("Radiatorkranen")
                + " (kies gewoon hun klimaat-entiteit).",
                "Kies <b>Verzenden</b>. De kamer staat meteen op de E32. Herhaal voor de volgende kamer."]),
         KeepTogether([
         p("Het dashboard", "h2"),
         p("Open in de zijbalk het dashboard <b>OpenThermostat</b>. Het heeft zes tabbladen:"),
         # The names that come with HA 1.0.0rc6 (docs/modern-thermostat/RC5-DASHBOARD-SPEC.md) are plain <b> until they are in the
         # Dutch dashboard texts of dashboard.py (Overige ruimtes, Vandaag en deze week, Wat de ketel meldt, Gisteren in cijfers, Wie
         # regelt de ketel) or in translations/nl.json (Wat de E32 weet, Watertemperatuur bij buitentemperatuur). Then move them
         # into ui() so that tools/dev/test_manual_labels.py checks them.
         table([["Tabblad", "Wat je ziet"],
                [ui("Overzicht"), "Bovenaan de <b>huiskaart</b>: een strook in de kleur van wat de ketel nu doet (verwarmt, warm water of in rust), "
                 "met de huismodus rechts. Bij een probleem wordt de strook rood met de reden; een tik brengt je bij Reparaties. Onder de strook "
                 "staan de cijfers van vandaag (verwarming, warm water, gas met de laatste 7 dagen, branderstarts) en de dag tot nu toe als balk. "
                 "Daaronder komen de huismodus, de volgende vakantie en een kaart per ruimte die in één regel zegt waarom ze verwarmt of niet. "
                 "Staat er maar één ruimte aan, dan zit die in de huiskaart en staan de andere onder " + ui("Overige ruimtes") + "."],
                [ui("Ruimtes"), "Per ruimte de thermostaat, de dag, de sensoren, ramen en personen, en wat de E32 leerde."],
                [ui("Weekprogramma"), "De weekplanner voor alle ruimtes."],
                [ui("Ketel"), "In de volgorde van wat je nodig hebt: " + ui("Nu") + " (wat de ketel doet, met de displaycode, de watertemperaturen "
                 "en het brandervermogen), " + ui("Advies") + ", " + ui("Vandaag en deze week") + " (gas en branderstarts van vandaag, met één grafiek "
                 "met het gas per dag van de laatste week), " + ui("Warm water") + ", " + ui("Afgelopen 24 uur") + ", " + ui("Wat de ketel meldt") + " en "
                 + ui("Ketelinstellingen") + ". Een onderdeel verschijnt pas als de ketel er iets voor meldt. Gisteren staat hier niet; dat vind "
                 "je bij " + ui("Leren en instellingen") + "."],
                [ui("Leren en instellingen"), "Hier lees je wat de E32 zelf leerde en deed: " + ui("Wat de E32 weet") + " en nog moet leren, met de reactie "
                 "van de ketel en gisteren vergeleken met normaal; " + ui("Gisteren in cijfers") + " (gisteren staat alleen hier); wat de "
                 "thermostaat leerde over je ruimtes, je huis en je ketel, met de gratis warmte; Slim opwarmen en de weerafhankelijke regeling "
                 "met de grafiek " + ui("Watertemperatuur bij buitentemperatuur") + "; en " + ui("Wie regelt de ketel") + ", met de controle voor de overname."],
                [ui("Diagnose"), "Voor het zoeken naar fouten, met ook " + ui("Thermostaat op de bus") + ": wat een andere thermostaat aan de ketel "
                 "vraagt, zoals de E32 het hoort."]],
               [48 * mm, W - 48 * mm])]),
         Spacer(1, 4),
         p("In de proefperiode (de E32 rekent mee maar stuurt de ketel nog niet) is er ook een onderdeel " + ui("Vergelijking")
           + ": de E32 naast je huidige thermostaat.", "small"),
         p("Weekprogramma aanpassen", "h2"),
         p("Open het tabblad " + ui("Weekprogramma") + ". Elke kamer heeft drie niveaus: "
           "<b>Comfort</b>, <b>Eco</b> en <b>Nacht</b>. Schilder blokken, sleep randen, kopieer een dag naar andere dagen. "
           "Een tijd in het programma betekent: <i>op die tijd warm</i>. De E32 begint zelf op tijd (Slim opwarmen)."),
         p("Huis en afwezigheid", "h2"),
         p("<b>Configureren</b> → " + ui("Huis", "Aanwezigheid en afwezigheidstemperatuur") + ": " + ui("Wie hier woont")
           + ", " + ui("Afwezig na") + " en " + ui("Temperatuur als niemand thuis is") + ". Is iedereen weg, "
           "dan gaan alle kamers naar die temperatuur."),
         p("De huismodus (" + named("Automatisch", "Thuis", "Afwezig", "Vakantie") + ") stel je in onder <b>Configureren</b> → "
           + ui("Huis", "Huismodus en vakantie", "Huismodus") + " (voor een vakantie die nu begint kies je ook " + ui("Vakantie eindigt")
           + "). De huismodus staat ook op het dashboard en op het apparaat. Vakanties vooruit plannen staat in hoofdstuk 10."),
         p("<b>Waterlimieten</b>: onder <b>Configureren</b> → " + ui("Verwarming en ketel", "Grenzen van de watertemperatuur")
           + ". Standaard 30–60 °C. Vloerverwarming zonder mengklep meestal hooguit 45–50 °C.", "small"),
         ])

    # ---- 9 Boiler test ---------------------------------------------------------------------------------
    add([PageBreak(), p("9. De keteltest en de overname", "h1"),
         p("Pas na deze stap regelt de E32 je ketel. Doe het met iemand bij de ketel, en reken op ongeveer 30 minuten. "
           "Je vindt alles op de E32-pagina <b>Ruimtes</b>, onder <b>Boiler test and takeover</b>."),
         box("Hoort de E32 nog een andere thermostaat op de ketel?",
             "Dan begint hij met een <b>proefperiode</b>: hij rekent mee en vergelijkt, maar stuurt niets. Je kunt die overslaan en "
             "direct de keteltest doen. Zonder thermostaat gaat hij meteen naar de keteltest."),
         steps(["<b>Start the boiler test</b>. De E32 vraagt eerst of je in de buurt van de ketel blijft, zodat je hem kunt "
                "uitzetten als er iets vreemd lijkt.",
                "<b>Geen andere thermostaat op de ketel.</b> Had je er een: ketel uit, thermostaat loskoppelen, ketel weer aan. "
                "Deze stap slaagt als de E32 2 minuten geen andere thermostaat hoort.",
                "<b>Overname bevestigen</b>: bevestig dat de E32 de ketel mag regelen.",
                "<b>Verwarmen starten</b>: de E32 zet één kamer tijdelijk ongeveer 1 °C hoger. De brander moet binnen 10 minuten aanslaan "
                "en het water minstens 3 °C warmer worden.",
                "<b>Warm water tijdens verwarmen</b>: draai 3 minuten een warme kraan open. Warm water gaat voor, daarna gaat het verwarmen verder. "
                "Een ketel zonder warm water slaat deze stap over.",
                "<b>Verwarmen stoppen</b>: de kamer gaat tijdelijk 0,5 °C lager. De brander moet uitgaan en 5 minuten uit blijven.",
                "<b>Klaar</b>: \"The E32 now controls your boiler.\" Het weekprogramma gaat gewoon verder."]),
         p("De E32 controleert elke stap zelf en toont hem als geslaagd, wachtend of mislukt, met wat je kunt doen. "
           "Gaat er iets mis, dan stopt hij de test en legt hij uit hoe je de regeling teruggeeft. "
           "Met <b>Stop the test</b> stop je zelf op elk moment."),
         p("De E32 <b>onthoudt</b> de uitslag, ook na een update. Heb je de test eerder al gedaan, dan kun je hem markeren met "
           "<b>I have already done this test</b>."),
         ])

    # ---- 10 and 11 After -------------------------------------------------------------------------------
    add([p("10. Na de ingebruikname", "h1"),
         p("De thermostaat draait nu zelf. Dit is goed om te weten:"),
         table([["Onderwerp", "Wat je moet weten"],
                ["Zelf leren", "De E32 leert hoe snel elke kamer opwarmt, met welke laagste watertemperatuur, en een weerafhankelijke regeling "
                 "voor jouw huis. <b>Slim opwarmen</b> en de <b>weerafhankelijke regeling</b> staan standaard aan. "
                 "Sinds rc.5 luistert hij ook naar je ketel en zegt hij hoeveel hij van je huis weet (de rijen hieronder). "
                 "Er is niets in te stellen: hij stelt zichzelf af en jij leest wat hij deed. "
                 "Wat hij leerde, zie je op het dashboardtabblad " + ui("Leren en instellingen") + " en op de E32 onder "
                 "<b>Huis → Wat de thermostaat heeft geleerd</b>. Aanpassen kan onder <b>Configureren</b> → "
                 + ui("Verwarming en ketel") + " (" + named("Slim opwarmen", "Weerafhankelijke regeling") + ")."],
                ["Slim opwarmen vanaf dag één", "Een tijd in het weekprogramma betekent: <i>op die tijd warm</i>. Slim opwarmen begint vanaf de eerste "
                 "ochtend op tijd met verwarmen, eerst met een <b>schatting</b> (vloerverwarming 2 uur per graad, radiatoren 45 minuten per graad; "
                 "hooguit 3 uur of 90 minuten vooruit). Je leest het aan \"begint om 07:40 (schatting; hij leert van elke ochtend)\". "
                 "Elke ochtend kijkt de E32 of de ruimte op tijd warm was. Meer dan 10 minuten te laat: de volgende start is 10 % eerder. "
                 "Meer dan 15 minuten te vroeg: 8 % later. Je ziet de uitkomst, bijvoorbeeld \"Gisteren warm om 09:12 (12 min te laat); "
                 "morgen 10 % eerder.\" De eerste ochtenden kan een ruimte dus iets te vroeg of te laat warm zijn."],
                ["Gisteren in cijfers", "Zodra de E32 een dag heeft gemeten, toont <b>Gisteren</b> hoe die dag ging: stooktijd, branderstarts per "
                 "stookuur, korte brandtijden, gas voor verwarmen (schatting), graaddagen en per ruimte hoeveel minuten te laat of te vroeg "
                 "ze warm was en hoeveel graden te warm. Home Assistant: dashboardtabblad " + ui("Leren en instellingen") + ", blok "
                 + ui("Gisteren in cijfers") + " (gisteren staat op het dashboard alleen daar). E32: <b>Huis → Wat de thermostaat heeft geleerd</b>, "
                 "blok <b>Gisteren</b>."],
                ["De E32 kent je huis", "Sinds rc.5 zegt de E32 hoeveel hij al van je huis weet: <b>De E32 kent je huis: 70 %</b>, met in gewone "
                 "woorden wat hij nog moet leren, bijvoorbeeld \"Hij moet nog zien hoe snel de woonkamer opwarmt\". Het getal stijgt vanzelf "
                 "terwijl de verwarming draait; het is alleen informatie en er is niets in te stellen. Home Assistant: dashboardtabblad "
                 + ui("Leren en instellingen") + ", bovenaan " + ui("Wat de E32 weet") + "; de sensoren " + ui("Kennis") + " en "
                 + ui("Reactie van de ketel") + " staan op het E32-apparaat. E32: <b>Huis → Wat de thermostaat heeft geleerd</b>."],
                ["Luisteren naar de ketel", "Haalt de ketel de gevraagde watertemperatuur en slaat hij zelf af terwijl een ruimte nog warmte wil, "
                 "dan vroeg de E32 meer dan het huis opneemt. Gebeurt dat twee keer in één warmtevraag, dan leert de E32 een <b>plafond</b> voor "
                 "de watertemperatuur (per bereik van de buitentemperatuur) en vraagt hij niet meer dan dat: koeler water en minder branderstarts. "
                 "Zolang de ruimte die het verst van haar doel zit 1 °C of meer te koud is, vraagt hij wel de volle watertemperatuur: een koude "
                 "ochtend wordt niet vertraagd door de beperkingen van gisteren. Ook leert hij hoe lang de ketel dan zelf rust, en houdt hij zijn eigen brandrust minstens zo lang (hooguit 15 minuten), tenzij een "
                 "ruimte meer dan 0,3 °C te koud is: comfort gaat voor. Dit gebeurt alleen terwijl de E32 de ketel regelt, het plafond ook alleen "
                 "met <b>Slim opwarmen</b> aan. Hij gebruikt alleen waarden die elke ketel meldt en verandert geen ketelinstelling. Meldt je ketel "
                 "de retourtemperatuur niet, dan ziet hij niet hoeveel warmte het huis opneemt; al het andere werkt gewoon. Je leest het in één "
                 "zin, bijvoorbeeld \"Je ketel rust ongeveer 6 min telkens als hij zijn temperatuur bereikt; de E32 vraagt nu hooguit 41 °C, "
                 "zodat hij minder vaak start.\""],
                ["Het huis en de weerafhankelijke regeling", "Uit hoe snel de ruimtes opwarmen en afkoelen (of uit het gas per graaddag) rekent de "
                 "E32 uit hoe snel je huis warmte verliest en hoeveel warmte radiatoren of vloer per graad watertemperatuur afgeven. Daarmee schat "
                 "hij de <b>weerafhankelijke regeling</b> al voordat hij zes rustige stookperiodes van drie uur heeft gezien, nooit minder dan half "
                 "zo steil als de standaardlijn. De pagina's zeggen het: \"Weerafhankelijke regeling: voorlopig geschat uit je huis, hij leert nog "
                 "bij (2 van 6 rustige periodes).\" De grafiek " + ui("Watertemperatuur bij buitentemperatuur") + " toont de standaardlijn (gestippeld), "
                 "de lijn die voor je huis is geleerd (doorgetrokken), het punt van nu en de watertemperatuur bij −10 °C. Home Assistant: "
                 "dashboardtabblad " + ui("Leren en instellingen") + ". E32: <b>Huis → Verwarming → Watertemperatuur</b>."],
                ["Gisteren vergeleken met normaal", "Vanaf de vijfde dag vergelijkt de E32 gisteren met de gewone dagen van je eigen huis: gas per "
                 "graad kou, branderstarts per stookuur, stookuren per graad kou en per ruimte de opwarmtijd. Wijkt iets meer dan 30 % af, dan "
                 "staat er één gewone zin met wat het kan veroorzaken, bijvoorbeeld \"Gisteren ging er 35 % meer gas per graad kou door dan "
                 "normaal.\" Het is alleen informatie: nooit een storing en nooit een reparatie. Home Assistant: een melding per zin (weg te "
                 "klikken) en de lijst <b>Gisteren vergeleken met normaal</b> op het tabblad " + ui("Leren en instellingen") + ". E32: "
                 "<b>Huis → Wat de thermostaat heeft geleerd</b>."],
                ["Gratis warmte", "Zon, koken en mensen verwarmen een ruimte zonder ketel. De E32 leert dat per ruimte en per dagdeel van vier uur. "
                 "Vanaf vijf metingen in een dagdeel begint Slim opwarmen in dat dagdeel later: de voorlooptijd wordt korter, nooit tot minder dan "
                 "de helft, en de ochtendcontrole blijft elke start beoordelen. Je leest het bij de ruimte op de E32-pagina (Home Assistant "
                 "toont het alleen als het bericht van de E32 voor die ruimte er plaats voor heeft): \"'s Middags warmt deze ruimte vanzelf op, "
                 "ongeveer 0,4 °C per uur (zon, koken of mensen).\""],
                ["Waarom verwarmt een ruimte?", "Op de E32-pagina <b>Overzicht</b> zegt elke ruimte in één regel waarom ze verwarmt of niet, "
                 "in dezelfde woorden als Home Assistant, bijvoorbeeld \"Warm genoeg: 21 °C (gewenst 21 °C)\", \"Gepauzeerd: er staat een raam "
                 "of deur open\" of \"Slim opwarmen: nu al verwarmen voor 08:00 (21 °C)\". Dat werkt ook zonder Home Assistant."],
                ["Vakantie plannen", "Plan vakanties vooruit (hooguit 8), elk met een begin en een einde (weer thuis). Een vakantie begint en "
                 "eindigt vanzelf: ondertussen wordt elke ruimte hooguit zo warm als de <b>vakantietemperatuur</b> (de vorstbeveiliging blijft aan), "
                 "het huis is op tijd weer warm als je terugkomt, en daarna staat de huismodus weer zoals ervoor. Home Assistant: <b>Configureren</b> → "
                 + ui("Huis", "Huismodus en vakantie") + ", daar " + ui("Vakantie plannen") + " (kies " + ui("Begint") + " en "
                 + ui("Eindigt (weer thuis)") + "; het einde ligt hooguit een jaar vooruit) en " + ui("Temperatuur op vakantie")
                 + " (5–25 °C; tot je die instelt is het de afwezigheidstemperatuur). Wijzigen of verwijderen kan met "
                 + ui("Vakantie wijzigen of verwijderen") + "; een lopende vakantie stop je met " + ui("Vakantie stoppen")
                 + " onder <b>Configureren</b> → " + ui("Huis") + ". Op de E32: pagina <b>Huis</b>, blok <b>Vakanties</b> "
                 "(<b>Vakantie toevoegen</b> met <b>Van</b> en <b>Tot</b>, <b>Vakantie opslaan</b>, <b>Temperatuur op vakantie (°C)</b>). "
                 "Beide plekken wijzigen dezelfde lijst. Een vakantie heeft de klok van de E32 nodig."],
                ["Zelfafstelling", "Branderrust, brandtijd en marges stelt hij zelf af, met hooguit één kleine stap per dag. "
                 "Na een herstart wacht hij eerst 2 uur, na de eerste start of een wijziging die de regeling raakt 24 uur."],
                ["Updates", f"Eerst de integratie ({HA_VERSION}) in HACS (met <b>Pre-release</b> aan) en Home Assistant herstarten, dan de firmware via de "
                 "entiteit " + ui("Firmware") + " (<b>Instellingen → Updates</b>). Doe dit als er iemand thuis is. Wat rc.5 toevoegt (ketel, huis, "
                 "gratis warmte) begint bij nul en vult zich in de eerste stookdagen; het getal van <b>De E32 kent je huis</b> begint dus lager."],
                ["Na elke firmware-update", "<b>Bevestig de overname opnieuw</b>: Reparatie " + ui("Bevestig opnieuw dat de E32 de ketel mag regelen")
                 + " (<b>Instellingen → Systeem → Reparaties</b>), of Ruimtes op de E32. Tot dan houdt de E32 alleen vorstbeveiliging aan."],
                ["Back-up", "Home Assistant maakt dagelijks een back-up van de E32-instellingen, inclusief geplande vakanties en wat hij geleerd heeft "
                 "(7 dagen bewaard). Wat hij van je ketel leerde (plafond en rust) zit er niet in; dat leert hij binnen enkele dagen opnieuw. "
                 "Zelf maken kan op <b>Systeem → Backup and restore</b>."],
                ["Afmelden", "Onderaan het menu <b>Systeem</b> staat <b>Afmelden</b>, zodra je bent aangemeld. Daarmee sluit je je sessie op de E32."],
                ["Problemen zien", "Op het tabblad " + ui("Overzicht") + " wordt de strook van de huiskaart rood met \"Let op\" en de eerste reden; een tik "
                 "brengt je bij Reparaties. Elk probleem staat ook onder <b>Instellingen → Systeem → Reparaties</b>. Een blauwdruk stuurt "
                 "desgewenst een melding naar je telefoon."]],
               [42 * mm, W - 42 * mm]),
         p("Terug naar je oude thermostaat?", "h2"),
         p("Kan altijd: op de E32 <b>Ruimtes → Active control</b> → regeling teruggeven, en de oude thermostaat weer aansluiten. "
           "Stap voor stap: " + a(DOCS + "SWITCHOVER.md", "overstap- en terugzetprocedure") + "."),
         p("11. Meer hulp en links", "h1"),
         table([["Wat", "Link"],
                ["Releases (firmware en integratie)", a(REL)],
                ["Volledige installatiegids (Engels)", a(DOCS + "INSTALL.md")],
                ["Gebruikershandleiding (Engels)", a(DOCS + "USER-GUIDE.md")],
                ["HACS-repository", a("https://github.com/dielessen/openthermostat-ha")],
                ["ESPConnect (flashen in de browser)", a("https://thelastoutpostworkshop.github.io/ESPConnect/")],
                ["BBQKees wiki", a("https://bbqkees-electronics.nl/wiki/")],
                ["HACS installeren", a("https://hacs.xyz/docs/use/")],
                ["Mosquitto-broker", a("https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md")],
                ["Wachtwoord vergeten / wifi herstellen", a(DOCS + "INSTALL.md#16-forgotten-password-and-wi-fi-recovery-over-usb", "INSTALL.md, hoofdstuk 16")],
                ["Problemen oplossen", a(DOCS + "INSTALL.md#17-troubleshooting", "INSTALL.md, hoofdstuk 17")]],
               [62 * mm, W - 62 * mm]),
         ])
    return story


def missing_characters(fonts):
    """Characters used in the text that the chosen fonts do not have (they would print as empty boxes)."""
    def lacks(font, text):
        have = pdfmetrics.getFont(font).face.charToGlyph
        return {ch for ch in text if ord(ch) not in have and not ch.isspace()}

    monospaced = ""
    running = ""
    for text in SEEN:
        monospaced += "".join(re.findall(r"<font name='Mono'>(.*?)</font>", text))
        running += re.sub(r"<font name='Mono'>.*?</font>", "", text)
    plain = re.sub(r"<[^>]+>", "", running).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    mono = monospaced.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    found = {}
    for font in ("Sans", "Sans-Bold", "Sans-Italic"):
        found[fonts[font]] = lacks(font, plain)
    found[fonts["Mono"]] = lacks("Mono", mono)
    return {file: "".join(sorted(chars)) for file, chars in found.items() if chars}


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Sans", 8.5); canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, f"OpenThermostat – handleiding installatie en ingebruikname (E32 {E32_VERSION} / HA {HA_VERSION})")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"pagina {doc.page}")
    canvas.restoreState()


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Dutch OpenThermostat installation manual as a PDF.")
    parser.add_argument("output", help="the PDF to write, for example out/OpenThermostat-Handleiding.pdf")
    parser.add_argument("--fonts", help="a folder with the fonts (Arial and Consolas, or DejaVu); tried first")
    args = parser.parse_args(argv)
    fonts = register_fonts(args.fonts)
    story = content()
    missing = missing_characters(fonts)
    if missing:
        sys.exit("These characters are not in the fonts, so they would print as boxes: "
                 + "; ".join(f"{file}: {chars}" for file, chars in missing.items()))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(args.output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title="OpenThermostat – Handleiding", author="OpenThermostat",
                            subject="Flashen, Home Assistant-integratie en ingebruikname van de E32")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print("ok", args.output)


if __name__ == "__main__":
    main()
