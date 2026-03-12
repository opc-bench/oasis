"""
OASIS Simulation Dashboard — Bloomberg Terminal Style
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OASIS Terminal",
    page_icon="🐦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Light theme CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Global white background */
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #ffffff;
    color: #14171a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }
  [data-testid="stSidebar"] {
    background-color: #f7f9fa;
    border-right: 1px solid #e1e8ed;
  }
  /* Section headers */
  h1, h2, h3 { color: #1da1f2 !important; letter-spacing: 0.5px; }
  /* Metric cards */
  [data-testid="metric-container"] {
    background-color: #f7f9fa;
    border: 1px solid #e1e8ed;
    border-radius: 8px;
    padding: 8px;
  }
  [data-testid="stMetricValue"] { color: #1da1f2 !important; font-size: 1.6rem !important; }
  [data-testid="stMetricLabel"] { color: #657786 !important; }
  /* Tweet cards — Twitter light style */
  .tweet-card {
    background-color: #ffffff;
    border: 1px solid #e1e8ed;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
    font-size: 0.90rem;
    line-height: 1.5;
    color: #14171a;
    transition: background 0.15s;
  }
  .tweet-card:hover { background-color: #f5f8fa; }
  .tweet-header { color: #657786; margin-bottom: 4px; font-size: 0.82rem; }
  .tweet-header .handle { color: #1da1f2; font-weight: 700; }
  .tweet-quote {
    background-color: #f7f9fa;
    border: 1px solid #e1e8ed;
    border-radius: 8px;
    margin-top: 8px;
    padding: 8px 12px;
    color: #657786;
    font-size: 0.82rem;
  }
  .tweet-meta { color: #aab8c2; font-size: 0.75rem; margin-top: 8px; display: flex; gap: 18px; }
  .tweet-meta span { display: flex; align-items: center; gap: 4px; }
  .tweet-meta .active { color: #e0245e; }
  .tweet-meta .active-blue { color: #1da1f2; }
  /* Action badge */
  .badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 12px;
    font-size: 0.68rem;
    font-weight: 700;
    margin-right: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .badge-create  { background: #e8f5e9; color: #2e7d32; }
  .badge-quote   { background: #fff8e1; color: #f57f17; }
  .badge-repost  { background: #e3f2fd; color: #1565c0; }
  .badge-like    { background: #fce4ec; color: #c62828; }
  .badge-follow  { background: #f3e5f5; color: #6a1b9a; }
  .badge-comment { background: #fff3e0; color: #e65100; }
  /* Section divider */
  .section-title {
    color: #1da1f2;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    border-bottom: 2px solid #1da1f2;
    padding-bottom: 4px;
    margin-bottom: 12px;
    margin-top: 8px;
  }
  /* Scrollable feed — phone-like */
  .feed-container {
    height: calc(100vh - 220px);
    min-height: 400px;
    overflow-y: auto;
    padding-right: 6px;
    padding-bottom: 16px;
  }
  /* Activity log rows */
  .log-row { font-size: 0.78rem; color: #657786; border-bottom: 1px solid #f0f3f4; padding: 5px 0; }
  .log-row .ts  { color: #aab8c2; min-width: 48px; display: inline-block; font-size: 0.72rem; }
  .log-row .uid { color: #1da1f2; font-weight: 600; min-width: 64px; display: inline-block; }
  /* Ticker bar */
  .ticker-bar {
    background: #ffffff;
    border: 1px solid #e1e8ed;
    border-radius: 8px;
    padding: 8px 16px;
    margin-bottom: 16px;
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    font-size: 0.80rem;
    color: #657786;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }
  .ticker-bar b { color: #1da1f2; }
  /* scrollbar */
  .feed-container::-webkit-scrollbar { width: 5px; }
  .feed-container::-webkit-scrollbar-track { background: #f7f9fa; }
  .feed-container::-webkit-scrollbar-thumb { background: #1da1f2; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────────
BADGE_MAP = {
    "create_post": "badge-create",
    "quote_post":  "badge-quote",
    "repost":      "badge-repost",
    "like":        "badge-like",
    "follow":      "badge-follow",
    "comment":     "badge-comment",
    "refresh":     "",
    "sign_up":     "",
}

AVATAR_COLORS = ["#1da1f2","#e0245e","#17bf63","#ffad1f","#794bc4",
                 "#f45d22","#00b2cc","#f91880","#00ba7c","#ff6600"]

def avatar(uid: int) -> str:
    color = AVATAR_COLORS[uid % len(AVATAR_COLORS)]
    initials = f"U{uid}"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;">'
        f'<span style="background:{color};color:#fff;border-radius:50%;'
        f'width:26px;height:26px;display:inline-flex;align-items:center;'
        f'justify-content:center;font-size:0.70rem;font-weight:700;">{initials}</span>'
        f'<span style="color:{color};font-weight:700;">@user{uid}</span>'
        f'</span>'
    )

def badge(action: str) -> str:
    cls = BADGE_MAP.get(action, "")
    if not cls:
        return ""
    return f'<span class="badge {cls}">{action.upper()}</span>'


@st.cache_resource
def get_conn(db_path: str):
    return sqlite3.connect(db_path, check_same_thread=False)


def load_data(db_path: str):
    conn = get_conn(db_path)
    users   = pd.read_sql("SELECT * FROM user", conn)
    posts   = pd.read_sql("SELECT * FROM post ORDER BY created_at", conn)
    traces  = pd.read_sql("SELECT * FROM trace ORDER BY created_at", conn)
    follows = pd.read_sql("SELECT * FROM follow", conn)
    likes   = pd.read_sql("SELECT * FROM like", conn)
    comments = pd.read_sql("SELECT * FROM comment", conn)
    return users, posts, traces, follows, likes, comments


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🟠 OASIS TERMINAL")
    st.markdown("---")

    db_files = list(Path(".").glob("**/*.db")) + list(Path("data").glob("**/*.db")) if Path("data").exists() else list(Path(".").glob("**/*.db"))
    db_options = [str(p) for p in db_files if ".venv" not in str(p)]

    if not db_options:
        st.error("No .db files found")
        st.stop()

    db_path = st.selectbox("DATABASE", db_options)
    st.markdown("---")
    auto_refresh = st.toggle("AUTO REFRESH", value=False)
    refresh_rate = st.slider("REFRESH INTERVAL (s)", 2, 30, 5)
    if auto_refresh:
        import time
        time.sleep(refresh_rate)
        st.rerun()

    st.markdown("---")
    st.markdown('<div style="color:#555;font-size:0.72rem;">OASIS Social Simulation<br>Bloomberg Terminal Style</div>', unsafe_allow_html=True)


# ─── Load data ────────────────────────────────────────────────────────────────
users, posts, traces, follows, likes, comments = load_data(db_path)

# Derived
action_traces = traces[~traces["action"].isin(["sign_up", "refresh"])].copy()
action_counts = action_traces["action"].value_counts()
total_posts   = len(posts[posts["content"].str.len() > 0])
total_actions = len(action_traces)
num_agents    = len(users)
num_follows   = len(follows)
num_likes     = len(likes)
num_comments  = len(comments)
sim_rounds    = int(traces["created_at"].max()) if len(traces) else 0

# ─── TOP TICKER BAR ───────────────────────────────────────────────────────────
st.markdown(f"""
<div class="ticker-bar">
  <span>🤖 <b>AGENTS</b> {num_agents}</span>
  <span>📝 <b>POSTS</b> {total_posts}</span>
  <span>⚡ <b>ACTIONS</b> {total_actions}</span>
  <span>👥 <b>FOLLOWS</b> {num_follows}</span>
  <span>❤️ <b>LIKES</b> {num_likes}</span>
  <span>💬 <b>COMMENTS</b> {num_comments}</span>
  <span>🔁 <b>SIM ROUNDS</b> {sim_rounds}</span>
  <span style="margin-left:auto;color:#aab8c2;">📂 {Path(db_path).name}</span>
</div>
""", unsafe_allow_html=True)

# ─── MAIN LAYOUT: 3 columns ───────────────────────────────────────────────────
col_feed, col_mid, col_right = st.columns([2, 1.8, 1.8])

# ════════════════════════════════════════════════════════
# LEFT: Twitter-style Feed
# ════════════════════════════════════════════════════════
with col_feed:
    st.markdown('<div class="section-title">◈ LIVE FEED</div>', unsafe_allow_html=True)

    filter_agent = st.selectbox(
        "FILTER BY AGENT",
        ["All agents"] + [f"user{i}" for i in sorted(users["user_id"].tolist())],
        key="feed_filter",
    )

    feed_posts = posts[posts["content"].str.len() > 0].copy()
    if filter_agent != "All agents":
        uid = int(filter_agent.replace("user", ""))
        feed_posts = feed_posts[feed_posts["user_id"] == uid]

    feed_posts = feed_posts.sort_values("created_at", ascending=False)

    import re
    import streamlit.components.v1 as components

    # Build a lookup: post_id -> (user_id, content) for resolving original posts
    post_lookup = {
        int(r["post_id"]): (int(r["user_id"]), str(r["content"]) if pd.notna(r["content"]) else "")
        for _, r in posts.iterrows()
    }

    def ht(text):
        """Highlight hashtags in blue."""
        return re.sub(r"(#\w+)", r'<span style="color:#1da1f2">\1</span>', text)

    def mini_avatar(uid: int) -> str:
        color = AVATAR_COLORS[uid % len(AVATAR_COLORS)]
        return (
            f'<span style="background:{color};color:#fff;border-radius:50%;'
            f'width:18px;height:18px;display:inline-flex;align-items:center;'
            f'justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;">U{uid}</span>'
        )

    cards_html = ""
    for _, row in feed_posts.iterrows():
        uid = int(row["user_id"])
        rnd = int(row["created_at"])
        is_quote  = pd.notna(row.get("quote_content")) and str(row.get("quote_content", "")).strip()
        is_repost = (not is_quote) and pd.notna(row.get("original_post_id"))
        act = "quote_post" if is_quote else ("repost" if is_repost else "create_post")
        shares = int(row["num_shares"]) if pd.notna(row["num_shares"]) else 0
        lk     = int(row["num_likes"])  if pd.notna(row["num_likes"])  else 0

        bdg = badge(act)
        av  = avatar(uid)
        shares_color = "#1da1f2" if shares > 0 else "#aab8c2"
        likes_color  = "#e0245e" if lk > 0 else "#aab8c2"

        if is_quote:
            # Main text = what THIS agent wrote (quote_content)
            main_text = ht(str(row["quote_content"]))

            # Nested box = the original post being quoted, with original author
            orig_uid, orig_content = None, str(row["content"]) if pd.notna(row["content"]) else ""
            orig_post_id = row.get("original_post_id")
            if pd.notna(orig_post_id) and int(orig_post_id) in post_lookup:
                orig_uid, orig_content = post_lookup[int(orig_post_id)]
            orig_author_html = (
                f'{mini_avatar(orig_uid)} <span style="color:{AVATAR_COLORS[orig_uid % len(AVATAR_COLORS)]};'
                f'font-weight:700;font-size:11px;">@user{orig_uid}</span> &nbsp;'
                if orig_uid is not None else ""
            )
            quoted_box = f"""
            <div style="background:#f7f9fa;border:1px solid #ccd6dd;border-radius:10px;
                        margin-top:10px;padding:10px 12px;font-size:13px;color:#657786;">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                {orig_author_html}
              </div>
              <div style="color:#14171a;">{ht(orig_content)}</div>
            </div>"""
        else:
            main_text = ht(str(row["content"]) if pd.notna(row["content"]) else "")
            quoted_box = ""
            # For reposts show original author hint
            if is_repost:
                orig_post_id = row.get("original_post_id")
                if pd.notna(orig_post_id) and int(orig_post_id) in post_lookup:
                    orig_uid, _ = post_lookup[int(orig_post_id)]
                    main_text = (
                        f'<span style="color:#657786;font-size:12px;">🔁 Reposted from @user{orig_uid}</span><br>'
                        + main_text
                    )

        cards_html += f"""
        <div style="background:#fff;border:1px solid #e1e8ed;border-radius:12px;
                    padding:14px 16px;margin-bottom:8px;font-size:14px;line-height:1.5;color:#14171a;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            {av}
            <span style="color:#aab8c2;font-size:12px;">{bdg} &nbsp;Round {rnd}</span>
          </div>
          <div style="color:#14171a;">{main_text}</div>
          {quoted_box}
          <div style="display:flex;gap:18px;margin-top:10px;font-size:12px;">
            <span style="color:{shares_color};">🔁 {shares}</span>
            <span style="color:{likes_color};">❤️ {lk}</span>
            <span style="color:#aab8c2;">💬 {int(row['num_dislikes']) if pd.notna(row['num_dislikes']) else 0}</span>
          </div>
        </div>"""

    # Use components.html to bypass Streamlit's markdown parser entirely
    feed_html = f"""
    <html><body style="margin:0;padding:0;background:#fff;">
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
      ::-webkit-scrollbar {{ width: 5px; }}
      ::-webkit-scrollbar-track {{ background: #f7f9fa; }}
      ::-webkit-scrollbar-thumb {{ background: #1da1f2; border-radius: 3px; }}
    </style>
    <div style="height:100%;overflow-y:auto;padding:2px 4px 16px 2px;box-sizing:border-box;">
      {cards_html}
    </div>
    </body></html>"""

    components.html(feed_html, height=680, scrolling=True)


# ════════════════════════════════════════════════════════
# MIDDLE: Charts
# ════════════════════════════════════════════════════════
with col_mid:
    # ── Action distribution donut ──────────────────────
    st.markdown('<div class="section-title">◈ ACTION DISTRIBUTION</div>', unsafe_allow_html=True)
    if len(action_counts) > 0:
        fig_donut = go.Figure(go.Pie(
            labels=action_counts.index,
            values=action_counts.values,
            hole=0.55,
            marker=dict(colors=["#1da1f2","#e0245e","#17bf63","#ffad1f","#794bc4","#f45d22","#00b2cc"]),
            textfont=dict(color="#333", size=11),
        ))
        fig_donut.update_layout(
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(color="#657786"),
            margin=dict(l=0, r=0, t=10, b=10),
            height=220,
            showlegend=True,
            legend=dict(font=dict(size=10, color="#657786"), bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("No actions yet")

    # ── Actions per round bar ─────────────────────────
    st.markdown('<div class="section-title">◈ ACTIVITY PER ROUND</div>', unsafe_allow_html=True)
    if len(action_traces) > 0:
        round_acts = action_traces.groupby(["created_at", "action"]).size().reset_index(name="count")
        fig_bar = px.bar(
            round_acts, x="created_at", y="count", color="action",
            color_discrete_sequence=["#1da1f2","#e0245e","#17bf63","#ffad1f","#794bc4","#f45d22"],
        )
        fig_bar.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f7f9fa",
            font=dict(color="#657786"),
            margin=dict(l=0, r=0, t=10, b=10),
            height=200,
            xaxis=dict(title="Round", gridcolor="#e1e8ed", color="#657786"),
            yaxis=dict(title="Count", gridcolor="#e1e8ed", color="#657786"),
            legend=dict(font=dict(size=9, color="#657786"), bgcolor="rgba(0,0,0,0)"),
            barmode="stack",
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    # ── Agent leaderboard ─────────────────────────────
    st.markdown('<div class="section-title">◈ AGENT LEADERBOARD</div>', unsafe_allow_html=True)
    post_counts = posts[posts["content"].str.len() > 0].groupby("user_id").size().reset_index(name="posts")
    share_sum   = posts.groupby("user_id")["num_shares"].sum().reset_index(name="shares")
    leaderboard = post_counts.merge(share_sum, on="user_id", how="left").fillna(0)
    leaderboard["agent"] = leaderboard["user_id"].apply(lambda x: f"user{x}")
    leaderboard = leaderboard.sort_values("posts", ascending=True).tail(10)

    fig_lb = go.Figure()
    fig_lb.add_trace(go.Bar(
        y=leaderboard["agent"], x=leaderboard["posts"],
        orientation="h", name="Posts",
        marker_color="#1da1f2",
    ))
    fig_lb.add_trace(go.Bar(
        y=leaderboard["agent"], x=leaderboard["shares"],
        orientation="h", name="Shares",
        marker_color="#17bf63",
    ))
    fig_lb.update_layout(
        paper_bgcolor="#ffffff", plot_bgcolor="#f7f9fa",
        font=dict(color="#657786"),
        margin=dict(l=0, r=0, t=10, b=10),
        height=250,
        xaxis=dict(gridcolor="#e1e8ed", color="#657786"),
        yaxis=dict(gridcolor="#e1e8ed", color="#657786"),
        legend=dict(font=dict(size=9, color="#657786"), bgcolor="rgba(0,0,0,0)"),
        barmode="group",
    )
    st.plotly_chart(fig_lb, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════
# RIGHT: Network + Activity Log
# ════════════════════════════════════════════════════════
with col_right:
    # ── Social graph ──────────────────────────────────
    st.markdown('<div class="section-title">◈ SOCIAL GRAPH</div>', unsafe_allow_html=True)

    try:
        import networkx as nx

        G = nx.DiGraph()
        for uid in users["user_id"]:
            G.add_node(int(uid))

        # Follow edges
        for _, r in follows.iterrows():
            G.add_edge(int(r["follower_id"]), int(r["followee_id"]), color="#794bc4", width=1.5)

        # Quote/repost edges (thinner)
        for _, r in action_traces[action_traces["action"].isin(["quote_post", "repost"])].iterrows():
            try:
                info = json.loads(r["info"])
                if "quoted_id" in info or "reposted_id" in info:
                    target_post_id = info.get("quoted_id") or info.get("reposted_id")
                    tp = posts[posts["post_id"] == target_post_id]
                    if len(tp):
                        target_uid = int(tp.iloc[0]["user_id"])
                        src_uid    = int(r["user_id"])
                        if src_uid != target_uid:
                            G.add_edge(src_uid, target_uid, color="#1da1f2", width=0.8)
            except Exception:
                pass

        pos = nx.spring_layout(G, seed=42, k=1.5)

        edge_traces = []
        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]; x1, y1 = pos[v]
            color = data.get("color", "#ccd6dd")
            width = data.get("width", 1)
            edge_traces.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="none", showlegend=False,
            ))

        node_x = [pos[n][0] for n in G.nodes()]
        node_y = [pos[n][1] for n in G.nodes()]
        node_text = [f"user{n}" for n in G.nodes()]
        node_colors = [AVATAR_COLORS[n % len(AVATAR_COLORS)] for n in G.nodes()]
        node_sizes  = [10 + G.degree(n) * 2 for n in G.nodes()]

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            text=node_text,
            textposition="top center",
            textfont=dict(size=8, color="#657786"),
            marker=dict(size=node_sizes, color=node_colors,
                        line=dict(width=1.5, color="#ffffff")),
            hoverinfo="text",
        )

        fig_net = go.Figure(data=edge_traces + [node_trace])
        fig_net.update_layout(
            paper_bgcolor="#ffffff", plot_bgcolor="#f7f9fa",
            margin=dict(l=0, r=0, t=0, b=0),
            height=280,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            showlegend=False,
        )
        st.plotly_chart(fig_net, use_container_width=True, config={"displayModeBar": False})

    except ImportError:
        st.warning("pip install networkx for graph view")

    # ── Agent detail panel ─────────────────────────────
    st.markdown('<div class="section-title">◈ AGENT DETAIL</div>', unsafe_allow_html=True)
    sel_uid = st.selectbox(
        "SELECT AGENT",
        sorted(users["user_id"].tolist()),
        format_func=lambda x: f"user{x}",
        key="agent_detail",
    )
    urow = users[users["user_id"] == sel_uid].iloc[0]
    bio  = str(urow["bio"]) if pd.notna(urow["bio"]) else "—"
    ua   = action_traces[action_traces["user_id"] == sel_uid]
    up   = posts[(posts["user_id"] == sel_uid) & (posts["content"].str.len() > 0)]

    c1, c2, c3 = st.columns(3)
    c1.metric("POSTS", len(up))
    c2.metric("ACTIONS", len(ua))
    c3.metric("FOLLOWERS", int(urow["num_followers"]))

    st.markdown(f'<div style="color:#657786;font-size:0.82rem;margin:8px 0;border-left:3px solid #1da1f2;padding-left:8px;">{bio}</div>', unsafe_allow_html=True)

    # ── Activity log ──────────────────────────────────
    st.markdown('<div class="section-title">◈ ACTIVITY LOG</div>', unsafe_allow_html=True)
    log_data = action_traces.sort_values("created_at", ascending=False).head(40)
    log_html = ""
    for _, r in log_data.iterrows():
        try:
            info = json.loads(r["info"])
            info_str = json.dumps(info)[:60] + "…" if len(json.dumps(info)) > 60 else json.dumps(info)
        except Exception:
            info_str = str(r["info"])[:60]
        act_badge = badge(r["action"]) if r["action"] in BADGE_MAP else r["action"]
        log_html += f"""
        <div class="log-row">
          <span class="ts">R{int(r['created_at'])}</span>
          <span class="uid">@user{int(r['user_id'])}</span>
          {act_badge} <span style="color:#aab8c2">{info_str}</span>
        </div>"""
    st.markdown(f'<div style="max-height:220px;overflow-y:auto;">{log_html}</div>', unsafe_allow_html=True)


# ─── Bottom row: Post volume timeline + quote propagation tree ────────────────
st.markdown("---")
bot_l, bot_r = st.columns(2)

with bot_l:
    st.markdown('<div class="section-title">◈ POST VOLUME TIMELINE</div>', unsafe_allow_html=True)
    vol = posts[posts["content"].str.len() > 0].groupby("created_at").size().reset_index(name="posts")
    fig_vol = go.Figure(go.Scatter(
        x=vol["created_at"], y=vol["posts"],
        mode="lines+markers",
        line=dict(color="#1da1f2", width=2),
        marker=dict(color="#1da1f2", size=6),
        fill="tozeroy",
        fillcolor="rgba(29,161,242,0.12)",
    ))
    fig_vol.update_layout(
        paper_bgcolor="#ffffff", plot_bgcolor="#f7f9fa",
        font=dict(color="#657786"),
        margin=dict(l=0, r=0, t=10, b=10),
        height=180,
        xaxis=dict(title="Round", gridcolor="#e1e8ed", color="#657786"),
        yaxis=dict(title="New Posts", gridcolor="#e1e8ed", color="#657786"),
    )
    st.plotly_chart(fig_vol, use_container_width=True, config={"displayModeBar": False})

with bot_r:
    st.markdown('<div class="section-title">◈ TOP VIRAL POSTS</div>', unsafe_allow_html=True)
    viral = posts[posts["content"].str.len() > 0].copy()
    viral["engagement"] = viral["num_shares"] + viral["num_likes"]
    viral = viral.nlargest(5, "engagement")[["post_id", "user_id", "content", "num_shares", "num_likes", "engagement"]]
    viral["author"] = viral["user_id"].apply(lambda x: f"user{x}")
    viral["preview"] = viral["content"].str[:60] + "…"

    fig_viral = go.Figure(go.Bar(
        y=viral["preview"], x=viral["engagement"],
        orientation="h",
        marker_color="#1da1f2",
        text=viral["author"],
        textposition="inside",
        textfont=dict(color="#fff", size=9),
    ))
    fig_viral.update_layout(
        paper_bgcolor="#ffffff", plot_bgcolor="#f7f9fa",
        font=dict(color="#657786"),
        margin=dict(l=0, r=0, t=10, b=10),
        height=180,
        xaxis=dict(title="Engagement", gridcolor="#e1e8ed", color="#657786"),
        yaxis=dict(gridcolor="#e1e8ed", color="#657786", tickfont=dict(size=9)),
    )
    st.plotly_chart(fig_viral, use_container_width=True, config={"displayModeBar": False})
