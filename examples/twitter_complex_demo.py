import asyncio
import os
import sqlite3

from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType

import oasis
from oasis import (ActionType, LLMAction, ManualAction,
                   generate_twitter_agent_graph)

# Use only first 10 rows of the CSV
import pandas as pd
SRC_CSV = "data/twitter_dataset/anonymous_topic_200_1h/False_Business_0.csv"
SLIM_CSV = "/tmp/oasis_10agents.csv"
df = pd.read_csv(SRC_CSV).head(10)
df.to_csv(SLIM_CSV, index=False)


def print_db_summary(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("\n" + "="*60)
    print("SIMULATION RESULTS")
    print("="*60)

    cur.execute("""
        SELECT p.post_id, u.name, p.content, p.num_likes, p.num_shares
        FROM post p JOIN user u ON p.user_id = u.user_id
        ORDER BY p.post_id
    """)
    posts = cur.fetchall()
    print(f"\n[POSTS] ({len(posts)} total)")
    for p in posts:
        print(f"  #{p['post_id']} @{p['name']}: {p['content'][:80]}")
        print(f"         likes={p['num_likes']} reposts={p['num_shares']}")

    cur.execute("""
        SELECT c.comment_id, u.name, c.content, p.content as post_content
        FROM comment c
        JOIN user u ON c.user_id = u.user_id
        JOIN post p ON c.post_id = p.post_id
        ORDER BY c.comment_id
    """)
    comments = cur.fetchall()
    print(f"\n[COMMENTS] ({len(comments)} total)")
    for c in comments:
        print(f"  @{c['name']} -> \"{c['post_content'][:40]}...\"")
        print(f"    \"{c['content'][:80]}\"")

    cur.execute("SELECT COUNT(*) as cnt FROM follow")
    print(f"\n[FOLLOWS] {cur.fetchone()['cnt']} follow relationships created")

    cur.execute("""
        SELECT action_type, COUNT(*) as cnt FROM trace
        GROUP BY action_type ORDER BY cnt DESC
    """)
    print(f"\n[ACTION BREAKDOWN]")
    for a in cur.fetchall():
        print(f"  {a['action_type']}: {a['cnt']}")

    conn.close()


async def main():
    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_STEPFUN_3_5_Flash,
    )

    available_actions = ActionType.get_default_twitter_actions()

    agent_graph = await generate_twitter_agent_graph(
        profile_path=SLIM_CSV,
        model=model,
        available_actions=available_actions,
    )

    db_path = "./data/twitter_complex_demo.db"
    os.environ["OASIS_DB_PATH"] = os.path.abspath(db_path)
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs("./data", exist_ok=True)

    env = oasis.make(
        agent_graph=agent_graph,
        platform=oasis.DefaultPlatformType.TWITTER,
        database_path=db_path,
    )
    await env.reset()

    print("\nStep 1: Inject controversial tweet...")
    await env.step({
        env.agent_graph.get_agent(0): ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": "AI will replace 80% of software engineers in 5 years. Adapt or become irrelevant. #AI #FutureOfWork"})
    })

    print("Step 2: First wave of reactions (agents 1-4)...")
    await env.step({
        agent: LLMAction()
        for _, agent in env.agent_graph.get_agents([1, 2, 3, 4])
    })

    print("Step 3: Counter-narrative...")
    await env.step({
        env.agent_graph.get_agent(5): ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": "Hot take: AI won't replace engineers who use AI. Skilled devs are more in demand than ever. #AI #Coding"})
    })

    print("Step 4: All agents react...")
    await env.step({
        agent: LLMAction()
        for _, agent in env.agent_graph.get_agents()
    })

    print("Step 5: Final round...")
    await env.step({
        agent: LLMAction()
        for _, agent in env.agent_graph.get_agents()
    })

    await env.close()
    print_db_summary(db_path)


if __name__ == "__main__":
    asyncio.run(main())
