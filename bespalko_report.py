#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Утренний отчёт ИП Беспалько (Eleborg WB) в Telegram.

Источник — веб-версия 10X (app.system10x.ru), API кабинета workspaceId=3673.
Раньше данные тянулись CSV-экспортом Google-таблицы; см. README.md.

Запуск:
  python3 bespalko_report.py            # печать отчёта за вчера, без отправки
  python3 bespalko_report.py --send     # отправить в группу
  python3 bespalko_report.py --date 29.08.2026 --send
  python3 bespalko_report.py --dump-json /tmp/rnp.json   # сырые ответы API
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

API = "https://app.system10x.ru"
WORKSPACE_ID = "3673"
X10_EMAIL = ""
X10_PASSWORD = ""
TG_BOT_TOKEN = ""
TG_CHAT_ID = "-4673090941"
MIN_ORDERS = 1   # SKU с нулём заказов за день в «Топ»/«Убытки» не показываем
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load_env(path):
    """Читает KEY=VALUE из api-keys.env, не перетирая уже заданное окружение."""
    if not path or not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def request(url, body=None, token=None, tries=5):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            return json.loads(_opener.open(req, timeout=60).read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError("%s -> HTTP %s: %s" % (url, e.code, e.read().decode()[:300]))
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise last


def login():
    if not X10_EMAIL or not X10_PASSWORD:
        sys.exit("нет X10_EMAIL / X10_PASSWORD (положи их в api-keys.env)")
    d = request(API + "/api/auth/login", {"email": X10_EMAIL, "password": X10_PASSWORD})
    return d["data"]["access_token"]


def fetch(target):
    """Свод по кабинету + карточки SKU за месяц целевой даты."""
    token = login()
    payload = {"month": target.month, "year": target.year, "filters": [],
               "buyoutType": "fact", "drrType": "orders", "checkType": "withoutSpp"}
    common = request("%s/api/wb-rnp/common?workspaceId=%s&sid=&noCache=true" % (API, WORKSPACE_ID),
                     payload, token)
    cards = request("%s/api/v2/wb-rnp/cards?workspaceId=%s&page=1&limit=200" % (API, WORKSPACE_ID),
                    dict(payload, sort="ordersSumRub"), token)
    return common, cards


# ---------- форматирование (совпадает со старой версией отчёта) ----------

def fmt_money(v):
    return "—" if v is None else f"{int(round(v)):,}".replace(",", " ") + "₽"


def fmt_int(v):
    return "—" if v is None else f"{int(round(v)):,}".replace(",", " ")


def fmt_pct(v, d=2):
    return "—" if v is None else f"{v:.{d}f}".replace(".", ",") + "%"


def pct_of(fact, plan):
    return None if not fact or not plan else fact / plan * 100


def short_art(a):
    return a.replace("вентилятор", "вент").replace("отпугиватель", "отпуг")


def day_row(daily, target):
    key = target.strftime("%Y-%m-%d")
    for row in daily or []:
        if str(row.get("date", ""))[:10] == key:
            return row
    return None


def g(row, *path):
    """Безопасный доступ: g(row, 'orders', 'sum')."""
    cur = row
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def build(common, cards, target):
    month = common.get("month", {})
    fact, plan, fcst = month.get("fact", {}), month.get("plan", {}), month.get("forecast", {})
    o_fact, o_plan, o_fcst = g(fact, "orders", "sum"), g(plan, "orders", "sum"), g(fcst, "orders", "sum")
    m_fact, m_plan, m_fcst = g(fact, "profit", "sum"), g(plan, "profit", "sum"), g(fcst, "profit", "sum")

    last = (target.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    L = [f"\U0001F4C5 {WEEKDAYS[target.weekday()]}, {target.day} {MONTHS_GEN[target.month]}"
         f" — день {target.day} из {last.day}", ""]

    if o_plan:
        L.append(f"\U0001F4CA Заказы: {fmt_money(o_fact)} / план {fmt_money(o_plan)}"
                 f" → {fmt_pct(pct_of(o_fact, o_plan), 1)}")
        L.append(f"   Прогноз месяца: {fmt_money(o_fcst)} ({fmt_pct(pct_of(o_fcst, o_plan), 1)} плана)")
    else:
        L.append(f"\U0001F4CA Заказы за месяц: {fmt_money(o_fact)}")
        L.append(f"   Прогноз месяца: {fmt_money(o_fcst)}")
    if m_plan:
        L.append(f"\U0001F4B0 Маржа: {fmt_money(m_fact)} / план {fmt_money(m_plan)}"
                 f" → {fmt_pct(pct_of(m_fact, m_plan), 1)}")
        L.append(f"   Прогноз маржа: {fmt_money(m_fcst)} ({fmt_pct(pct_of(m_fcst, m_plan), 1)} плана)")
    else:
        L.append(f"\U0001F4B0 Маржа за месяц: {fmt_money(m_fact)}")
        L.append(f"   Прогноз маржа: {fmt_money(m_fcst)}")
    if not o_plan and not m_plan:
        L.append("   ⚙️ План на месяц в 10X не заполнен")

    L += ["", "━━━━━━━━━━━━━━━"]
    d = day_row(common.get("daily"), target) or {}
    o_cnt, b_cnt = g(d, "orders", "quantity"), g(d, "buyouts", "quantity")
    buyout_pct = (b_cnt / o_cnt * 100) if o_cnt else None
    drr = g(d, "advBudget", "advPercent")
    marg = g(d, "profit", "margWithAdvPercent")
    L.append(f"KPI вчера ({target.strftime('%d.%m')}):")
    L.append(f"Заказы: {fmt_money(g(d, 'orders', 'sum'))} / {fmt_int(o_cnt)} шт")
    L.append(f"Выкупы: {fmt_money(g(d, 'buyouts', 'sum'))} / {fmt_int(b_cnt)} шт"
             f" ({fmt_pct(buyout_pct, 1)} выкупа)")
    L.append(f"Реклама: {fmt_money(g(d, 'advBudget', 'sum'))} /"
             f" ДРР: {fmt_pct(drr * 100 if drr is not None else None)}")
    L.append(f"Маржа: {fmt_money(g(d, 'profit', 'sum'))}"
             f" ({fmt_pct(marg * 100 if marg is not None else None)})")

    items = []
    for c in cards.get("data", []):
        row = day_row(c.get("daily"), target)
        if not row:
            continue
        mp = g(row, "profit", "margWithAdvPercent")
        cnt = g(row, "orders", "quantity") or 0
        if cnt < MIN_ORDERS:      # мелочь в списки не пускаем
            continue
        items.append({"art": (g(c, "cardData", "vendorCode") or str(c.get("nmId")) or "").strip(),
                      "orders_cnt": cnt,
                      "margin": g(row, "profit", "sum"),
                      "margin_pct": mp * 100 if mp is not None else None})

    pos = sorted([x for x in items if (x["margin"] or 0) > 0], key=lambda x: x["margin"], reverse=True)
    L += ["", "\U0001F3C6 Топ по марже:"]
    for it in pos[:3]:
        L.append(f"• {short_art(it['art'])}: {fmt_int(it['orders_cnt'])}шт /"
                 f" +{fmt_money(it['margin'])} ({fmt_pct(it['margin_pct'])})")
    neg = sorted([x for x in items if (x["margin"] or 0) < 0], key=lambda x: x["margin"])
    if neg:
        L += ["", "⚠️ Убытки:"]
        for it in neg:
            L.append(f"• {short_art(it['art'])}: {fmt_int(it['orders_cnt'])}шт /"
                     f" {fmt_money(it['margin'])} ({fmt_pct(it['margin_pct'])})")
    return "\n".join(L)


def send(text):
    if not TG_BOT_TOKEN:
        sys.exit("нет TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    ctx = ssl.create_default_context()
    resp = urllib.request.urlopen(urllib.request.Request(url, data=data),
                                  timeout=30, context=ctx).read()
    return json.loads(resp).get("ok", False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="ДД.ММ.ГГГГ, по умолчанию вчера")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--keys", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "api-keys.env"))
    ap.add_argument("--dump-json")
    a = ap.parse_args()

    load_env(a.keys)
    globals().update(
        X10_EMAIL=os.environ.get("X10_EMAIL", ""),
        X10_PASSWORD=os.environ.get("X10_PASSWORD", ""),
        TG_BOT_TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        TG_CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID", "-4673090941"),
        WORKSPACE_ID=os.environ.get("X10_WORKSPACE_ID", "3673"))

    target = (datetime.strptime(a.date, "%d.%m.%Y").date() if a.date
              else date.today() - timedelta(days=1))
    common, cards = fetch(target)
    if a.dump_json:
        json.dump({"common": common, "cards": cards},
                  open(a.dump_json, "w", encoding="utf-8"), ensure_ascii=False)
    msg = build(common, cards, target)
    sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
    if a.send:
        print("TG_OK=", send(msg))


if __name__ == "__main__":
    main()
