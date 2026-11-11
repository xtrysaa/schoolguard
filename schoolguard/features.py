"""Признаки v2: взаимодействие людей по скелетам + энергия движения. Чистая математика (numpy).

Все расстояния нормируются на «рост» человека, скорости — в «ростах в секунду», время — в секундах,
поэтому признаки не зависят от удалённости камеры и (почти) от частоты кадров.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np

from .tracker import Person

KP_CONF = 0.30
NOSE, L_EAR, R_EAR, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = \
    0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16
ARMS, LEGS = (L_EL, R_EL, L_WR, R_WR), (L_KN, R_KN, L_AN, R_AN)
TORSO_TO_HEIGHT = 3.3
JUMP_MAX_SPEED = 10.0     # рост/с: быстрее — это смена ID, а не движение человека
H_JUMP_RATIO = 1.8
LIMB_MAX_SPEED = 30.0     # рост/с: выше — шум позы
NEAR = 2.0                # «рядом»: ближе двух ростов
ENC_RADIUS = 1.8

FEATURE_NAMES = [
    "n_people",        # людей в кадре
    "min_dist",        # минимальная дистанция между людьми (в ростах)
    "closing_speed",   # скорость сближения пары
    "strike",          # скорость запястья в сторону другого человека
    "kick",            # скорость стопы в сторону другого человека
    "wrist_energy",    # энергия махов руками
    "wrist_jerk",      # рывок запястья (ускорение)
    "limb_speed_max",  # макс. скорость конечностей у людей, стоящих рядом с кем-то
    "limb_speed_mean",
    "pose_change",     # как быстро меняется поза (суставы относительно корпуса)
    "box_iou",         # перекрытие боксов ближайшей пары
    "intrusion",       # кисти/стопы одного внутри силуэта другого
    "hand_head",       # дистанция «кисть — голова другого»
    "encirclement",    # окружение одного человека группой
    "trapped",         # окружён и не может отойти
    "pursuit",         # преследование
    "distress_pose",   # падение / лежит / закрывается руками
    "torso_tilt",      # наклон корпуса от вертикали
    "tilt_rate",       # скорость изменения наклона
    "aspect_rate",     # скорость изменения формы бокса
    "pair_speed",      # скорость движения ближайшей пары
    "rel_speed",       # относительная скорость внутри пары
    "speed_max",       # макс. скорость человека
    "mot_pair",        # энергия движения в боксах ближайшей пары (пиксели)
    "mot_ratio",       # она же относительно всего кадра
    "mot_max",
    "gmot",            # энергия движения всего кадра (тряска камеры, толпа)
    "kp_conf_pair",    # уверенность ключевых точек пары (в клинче падает)
    "id_churn",        # доля новых треков (сцена «рассыпается»)
    "crowd_near",      # людей рядом с ближайшей парой
    "converge",        # окружающие движутся к паре
]
N_FEATURES = len(FEATURE_NAMES)
IDX = {n: i for i, n in enumerate(FEATURE_NAMES)}
STATS = ("mean", "max", "std", "min")
WINDOW_FEATURE_NAMES = [f"{n}_{s}" for s in STATS for n in FEATURE_NAMES] + ["n_frames_rate"]
WINDOW_S = 2.0


def _mid(a, b):
    if a is not None and b is not None:
        return (a + b) / 2
    return a if a is not None else b


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.zeros_like(v)


class FeatureState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.people: dict = {}
        self.pairs: dict = {}
        self.t = None
        self.seen: set = set()


def compute_frame_features(people: list[Person], state: FeatureState, t: float, gmot: float = 0.0):
    """-> (вектор признаков (N_FEATURES,), info) для одного кадра."""
    dt = None if state.t is None else t - state.t
    if dt is not None and dt < 1e-3:
        dt = None
    cur = {}
    new_ids = 0
    for p in people:
        k = p.kpts
        ok = k[:, 2] >= KP_CONF
        pt = lambda i: k[i, :2].astype(float) if ok[i] else None
        prev = state.people.get(p.id)
        if p.id not in state.seen:
            new_ids += 1
            state.seen.add(p.id)
        bw, bh = float(p.box[2] - p.box[0]), float(p.box[3] - p.box[1])
        box_h = max(bh, bw, 1.0)
        sh, hip = _mid(pt(L_SH), pt(R_SH)), _mid(pt(L_HIP), pt(R_HIP))
        if sh is not None and hip is not None:
            tl = float(np.linalg.norm(hip - sh)) * TORSO_TO_HEIGHT
            if 0.4 * box_h < tl < 1.3 * box_h:
                box_h = 0.5 * box_h + 0.5 * tl
        c = _mid(hip, sh)
        if c is None:
            c = np.array([(p.box[0] + p.box[2]) / 2, (p.box[1] + p.box[3]) / 2], float)
        if prev is not None and dt:                     # отсев смены ID
            jump = np.linalg.norm(c - prev["c"]) / max(prev["h"], 1.0) / dt
            ratio = max(box_h, prev["h"]) / max(min(box_h, prev["h"]), 1.0)
            if jump > JUMP_MAX_SPEED or ratio > H_JUMP_RATIO:
                prev = None
        h = box_h if prev is None else max(box_h, 0.97 * prev["h"])
        v = 0.6 * prev["v"] + 0.4 * (c - prev["c"]) / dt if (prev is not None and dt) else np.zeros(2)
        rel = np.full((17, 2), np.nan)                  # скорости суставов относительно корпуса (рост/с)
        if prev is not None and dt:
            both = ok & prev["ok"]
            rel[both] = ((k[both, :2] - prev["k"][both, :2]) / dt - v) / h
            bad = np.linalg.norm(rel, axis=1) > LIMB_MAX_SPEED
            rel[bad] = np.nan
        jerk = 0.0
        if prev is not None and dt:
            for w in (L_WR, R_WR):
                if not np.isnan(rel[w, 0]) and not np.isnan(prev["rel"][w, 0]):
                    jerk = max(jerk, float(np.linalg.norm(rel[w] - prev["rel"][w]) / dt))
        tilt, tilt_rate = 0.0, 0.0
        if sh is not None and hip is not None and np.linalg.norm(hip - sh) > 0.08 * h:
            tv = hip - sh
            tilt = float(np.arctan2(abs(tv[0]), abs(tv[1])) / (np.pi / 2))
            if prev is not None and dt and prev["tilt"] is not None:
                tilt_rate = abs(tilt - prev["tilt"]) / dt
        else:
            tilt = None
        aspect = float(np.log(max(bw, 1.0) / max(bh, 1.0)))
        aspect_rate = abs(aspect - prev["aspect"]) / dt if (prev is not None and dt) else 0.0
        head = pt(NOSE)
        if head is None:
            head = _mid(pt(L_EAR), pt(R_EAR))
        if head is None:
            head = sh
        head_vy = 0.0
        if prev is not None and dt and head is not None and prev["head"] is not None:
            head_vy = float(head[1] - prev["head"][1]) / dt
        cur[p.id] = dict(c=c, v=v, h=h, k=k, ok=ok, rel=rel, jerk=jerk, tilt=tilt, tilt_rate=tilt_rate, aspect=aspect,
                         aspect_rate=aspect_rate, head=head, head_vy=head_vy, sh=sh, hip=hip, box=p.box, mot=p.mot,
                         fresh=(prev is None and p.id in state.people), kc=float(k[:, 2].mean()))

    ids = list(cur)
    n = len(ids)
    f = np.zeros(N_FEATURES)
    f[IDX["n_people"]] = n
    f[IDX["min_dist"]] = 5.0
    f[IDX["hand_head"]] = 3.0
    f[IDX["gmot"]] = gmot
    f[IDX["id_churn"]] = new_ids / max(n, 1) if state.t is not None else 0.0
    info = dict(victim_id=None, pair=None)
    if n:
        f[IDX["speed_max"]] = min(max(np.linalg.norm(cur[i]["v"]) / cur[i]["h"] for i in ids), 8.0)
        f[IDX["mot_max"]] = max(cur[i]["mot"] for i in ids)

    new_pairs, best, closing = {}, None, 0.0
    for a, b in combinations(ids, 2):
        d = float(np.linalg.norm(cur[a]["c"] - cur[b]["c"]) / ((cur[a]["h"] + cur[b]["h"]) / 2))
        key = (min(a, b), max(a, b))
        new_pairs[key] = d
        if best is None or d < best[0]:
            best = (d, a, b)
        if key in state.pairs and dt and not (cur[a]["fresh"] or cur[b]["fresh"]):
            closing = max(closing, (state.pairs[key] - d) / dt)
    if best is not None:
        f[IDX["min_dist"]] = min(best[0], 5.0)
        f[IDX["closing_speed"]] = float(np.clip(closing, 0, 6))

    if n >= 2:
        near = {i: [o for o in ids if o != i and np.linalg.norm(cur[o]["c"] - cur[i]["c"]) / cur[i]["h"] < NEAR] for i in ids}
        strike = kick = wen = jerk = hand_head = 0.0
        hand_head = 3.0
        intr = 0
        limb_speeds, pose_ch = [], 0.0
        for i in ids:
            pi = cur[i]
            sp = np.linalg.norm(pi["rel"], axis=1)       # (17,) nan где нет данных
            if near[i]:
                lim = sp[list(ARMS + LEGS)]
                lim = lim[~np.isnan(lim)]
                if len(lim):
                    limb_speeds.append(float(lim.max()))
                allv = sp[~np.isnan(sp)]
                if len(allv) >= 6:
                    pose_ch = max(pose_ch, float(allv.mean()))
                jerk = max(jerk, pi["jerk"])
            wr_e = [0.5 * float(sp[w] ** 2) for w in (L_WR, R_WR) if not np.isnan(sp[w])]
            if wr_e:
                wen = max(wen, float(np.mean(wr_e)))
            for j in ids:
                if j == i:
                    continue
                pj = cur[j]
                x1, y1, x2, y2 = pj["box"]
                mx, my = 0.1 * (x2 - x1), 0.05 * (y2 - y1)
                for kp in (L_WR, R_WR, L_AN, R_AN):
                    if not pi["ok"][kp]:
                        continue
                    w = pi["k"][kp, :2].astype(float)
                    vec = pj["c"] - w
                    dist = np.linalg.norm(vec)
                    if x1 + mx < w[0] < x2 - mx and y1 + my < w[1] < y2 - my and dist / pj["h"] < 0.6:
                        intr += 1
                    if not np.isnan(sp[kp]) and dist > 1e-6 and dist / pi["h"] < 1.2:
                        toward = float(pi["rel"][kp] @ (vec / dist))
                        if kp in (L_WR, R_WR):
                            strike = max(strike, toward)
                        else:
                            kick = max(kick, toward)
                    if kp in (L_WR, R_WR) and pj["head"] is not None:
                        hand_head = min(hand_head, float(np.linalg.norm(w - pj["head"]) / pj["h"]))
        f[IDX["strike"]] = float(np.clip(strike, 0, 8))
        f[IDX["kick"]] = float(np.clip(kick, 0, 8))
        f[IDX["wrist_energy"]] = min(wen, 20.0)
        f[IDX["wrist_jerk"]] = min(jerk, 60.0)
        f[IDX["limb_speed_max"]] = min(max(limb_speeds), 12.0) if limb_speeds else 0.0
        f[IDX["limb_speed_mean"]] = min(float(np.mean(limb_speeds)), 12.0) if limb_speeds else 0.0
        f[IDX["pose_change"]] = min(pose_ch, 8.0)
        f[IDX["intrusion"]] = min(intr, 6) / 6
        f[IDX["hand_head"]] = min(hand_head, 3.0)

        # ---- ближайшая пара ----
        _, a, b = best
        pa, pb = cur[a], cur[b]
        info["pair"] = (a, b)
        ix = max(0.0, min(pa["box"][2], pb["box"][2]) - max(pa["box"][0], pb["box"][0]))
        iy = max(0.0, min(pa["box"][3], pb["box"][3]) - max(pa["box"][1], pb["box"][1]))
        ua = (pa["box"][2] - pa["box"][0]) * (pa["box"][3] - pa["box"][1]) + (pb["box"][2] - pb["box"][0]) * (pb["box"][3] - pb["box"][1]) - ix * iy
        f[IDX["box_iou"]] = ix * iy / max(ua, 1e-6)
        hh = (pa["h"] + pb["h"]) / 2
        f[IDX["pair_speed"]] = min(float(np.linalg.norm((pa["v"] + pb["v"]) / 2) / hh), 8.0)
        f[IDX["rel_speed"]] = min(float(np.linalg.norm(pa["v"] - pb["v"]) / hh), 8.0)
        mp = (pa["mot"] + pb["mot"]) / 2
        f[IDX["mot_pair"]] = mp
        f[IDX["mot_ratio"]] = float(np.log1p(min(mp / (gmot + 2e-3), 50.0)))
        f[IDX["kp_conf_pair"]] = (pa["kc"] + pb["kc"]) / 2
        mid = (pa["c"] + pb["c"]) / 2
        others = [cur[o] for o in ids if o not in (a, b)]
        f[IDX["crowd_near"]] = min(sum(np.linalg.norm(o["c"] - mid) / hh < 3.0 for o in others), 8)
        conv = [float(o["v"] @ _unit(mid - o["c"])) / o["h"] for o in others if np.linalg.norm(o["c"] - mid) / hh < 6.0]
        f[IDX["converge"]] = float(np.clip(np.mean(conv), -3, 3)) if conv else 0.0

        # ---- наклон корпуса, падение, защитная поза (только рядом с другим человеком) ----
        tilt = tr = ar = distress = 0.0
        distress_id = None
        for i in ids:
            pi = cur[i]
            if not near[i]:
                continue
            if pi["tilt"] is not None:
                tilt, tr = max(tilt, pi["tilt"]), max(tr, pi["tilt_rate"])
            ar = max(ar, pi["aspect_rate"])
            lying = 1.0 if (pi["tilt"] is not None and pi["tilt"] > 0.67) else 0.0
            fall = float(np.clip(pi["head_vy"] / pi["h"] / 3.0, 0, 1))
            defensive = 0.0
            if pi["ok"][NOSE]:
                cnt = sum(1 for w in (L_WR, R_WR) if pi["ok"][w]
                          and np.linalg.norm(pi["k"][w, :2] - pi["k"][NOSE, :2]) < 0.25 * pi["h"])
                defensive = (0.0, 0.4, 0.8)[cnt]
            s = max(0.8 * lying, fall, defensive)
            if s > distress:
                distress, distress_id = s, i
        f[IDX["torso_tilt"]], f[IDX["tilt_rate"]], f[IDX["aspect_rate"]] = tilt, min(tr, 6.0), min(ar, 6.0)
        f[IDX["distress_pose"]] = distress
        info["victim_id"] = distress_id

        # ---- преследование ----
        purs = 0.0
        for i in ids:
            pf = cur[i]
            speed = np.linalg.norm(pf["v"]) / pf["h"]
            if speed < 0.8:
                continue
            uf = _unit(pf["v"])
            kcount = 0
            for o in ids:
                if o == i:
                    continue
                po = cur[o]
                if np.linalg.norm(po["v"]) / po["h"] < 0.5:
                    continue
                if float(_unit(po["v"]) @ uf) > 0.7 and float((pf["c"] - po["c"]) @ uf) > 0 \
                        and np.linalg.norm(pf["c"] - po["c"]) / pf["h"] < 4:
                    kcount += 1
            if kcount:
                purs = max(purs, min(kcount, 3) / 3 * min(speed / 2.0, 1.0))
        f[IDX["pursuit"]] = purs

    if n >= 3:                                            # окружение: угловое покрытие соседей
        enc = trapped = 0.0
        enc_victim = None
        for vid in ids:
            pv = cur[vid]
            vecs = [cur[o]["c"] - pv["c"] for o in ids if o != vid
                    and np.linalg.norm(cur[o]["c"] - pv["c"]) / pv["h"] < ENC_RADIUS]
            if len(vecs) < 2:
                continue
            ang = np.sort(np.arctan2([d[1] for d in vecs], [d[0] for d in vecs]))
            gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
            e = (1 - gaps.max() / (2 * np.pi)) * min(len(vecs), 3) / 3
            if e > enc:
                enc, enc_victim = e, vid
                group_c = np.mean([pv["c"] + d for d in vecs], axis=0)
                away = max(0.0, float(pv["v"] @ _unit(pv["c"] - group_c))) / pv["h"]
                trapped = e * (1 - min(away, 1.0))
        f[IDX["encirclement"]], f[IDX["trapped"]] = enc, trapped
        if enc >= f[IDX["distress_pose"]] and enc_victim is not None:
            info["victim_id"] = enc_victim

    state.people, state.pairs, state.t = cur, new_pairs, t
    return f, info


def aggregate_window(rows: np.ndarray, duration: float = WINDOW_S) -> np.ndarray:
    """(T, F) покадровых признаков за окно -> вектор [mean | max | std | min | кадров/с]."""
    rows = np.asarray(rows, float)
    return np.concatenate([rows.mean(0), rows.max(0), rows.std(0), rows.min(0), [len(rows) / max(duration, 1e-6)]])


# ------------------------------------------------------------------ объяснимые сигналы (для интерфейса)
SIGNALS = {
    "strikes": "Удары и резкие движения рук/ног",
    "contact": "Захват, плотный контакт",
    "fall": "Падение, защитная поза",
    "encirclement": "Окружение одного человека",
    "pursuit": "Преследование",
    "motion": "Всплеск движения в зоне контакта",
}
SIGNAL_WEIGHTS = {"strikes": 0.30, "contact": 0.20, "fall": 0.20, "encirclement": 0.10, "pursuit": 0.08, "motion": 0.12}


def signals(f: np.ndarray) -> dict:
    """Нормированные сигналы [0..1] из одного кадра признаков: «почему» система подняла риск."""
    g = lambda n: float(f[IDX[n]])
    c = lambda x: float(np.clip(x, 0, 1))
    gate = c((2.0 - g("min_dist")) / 1.0)
    return {
        "strikes": gate * c(0.45 * c(g("strike") / 3.0) + 0.2 * c(g("kick") / 3.0) + 0.2 * c(g("limb_speed_max") / 5.0)
                           + 0.15 * c(g("wrist_jerk") / 25.0)),
        "contact": gate * c(0.5 * c(g("box_iou") / 0.35) + 0.3 * g("intrusion") * 2 + 0.2 * c((0.6 - g("hand_head")) / 0.6)),
        "fall": c(0.7 * g("distress_pose") + 0.3 * c(g("tilt_rate") / 2.0)),
        "encirclement": c(0.6 * g("encirclement") + 0.4 * g("trapped")),
        "pursuit": c(g("pursuit")),
        "motion": gate * c((g("mot_ratio") - 1.2) / 2.0),
    }


def heuristic_score(sig: dict) -> float:
    base = sum(SIGNAL_WEIGHTS[k] * sig[k] for k in SIGNAL_WEIGHTS)
    active = sum(sig[k] >= 0.4 for k in ("strikes", "contact", "fall", "encirclement", "pursuit"))
    return float(base * (0.65 + 0.35 * min(active, 2) / 2))
