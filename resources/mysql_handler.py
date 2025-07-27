# --------------------------------------------- #
# Plugin Name           : Telegram Support Bot  #
# Author Name           : fabston               #
# File Name             : mysql_handler.py      #
# --------------------------------------------- #

import pymysql
import config
from datetime import datetime

# ------------- Connection ------------- #
def getConnection():
    return pymysql.connect(
        host=config.mysql_host,
        user=config.mysql_user,
        password=config.mysql_pw,
        db=config.mysql_db,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

# ------------- Migration Helpers ------------- #
def _table_exists(cur, name):
    cur.execute("SHOW TABLES LIKE %s", (name,))
    return cur.fetchone() is not None

def _column_exists(cur, table, column):
    cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    return cur.fetchone() is not None

def run_migrations():
    """
    Create/alter all required tables & columns.
    Safe to call every start (idempotent).
    """
    conn = getConnection()
    try:
        with conn.cursor() as c:
            # USERS
            if not _table_exists(c, "users"):
                c.execute("""
                    CREATE TABLE users (
                      userid            BIGINT      NOT NULL PRIMARY KEY,
                      open_ticket       TINYINT(1)  NOT NULL DEFAULT 0,
                      banned            TINYINT(1)  NOT NULL DEFAULT 0,
                      open_ticket_spam  INT         NOT NULL DEFAULT 1,
                      open_ticket_link  VARCHAR(255)        DEFAULT NULL,
                      open_ticket_time  DATETIME    NOT NULL DEFAULT '1000-01-01 00:00:00',
                      claimed_by        BIGINT              DEFAULT NULL,
                      claim_time        DATETIME            DEFAULT NULL,
                      language          VARCHAR(5)          DEFAULT NULL,
                      current_ticket_id BIGINT              DEFAULT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                if not _column_exists(c, "users", "claim_time"):
                    c.execute("ALTER TABLE users ADD COLUMN claim_time DATETIME NULL AFTER claimed_by")
                if not _column_exists(c, "users", "current_ticket_id"):
                    c.execute("ALTER TABLE users ADD COLUMN current_ticket_id BIGINT NULL AFTER language")

            # AGENTS
            if not _table_exists(c, "agents"):
                c.execute("""
                    CREATE TABLE agents (
                      id               INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
                      user_id          BIGINT        NOT NULL UNIQUE,
                      full_name        VARCHAR(100)           DEFAULT NULL,
                      languages        TEXT                   DEFAULT NULL,
                      availability     TEXT                   DEFAULT NULL,
                      commission_rate  DECIMAL(6,4)  NOT NULL DEFAULT 0,
                      total_earnings   DECIMAL(12,2) NOT NULL DEFAULT 0,
                      tickets_claimed  INT           NOT NULL DEFAULT 0,
                      tickets_resolved INT           NOT NULL DEFAULT 0,
                      approved_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                for col, ddl in [
                    ("commission_rate",  "ALTER TABLE agents ADD COLUMN commission_rate  DECIMAL(6,4)  NOT NULL DEFAULT 0"),
                    ("total_earnings",   "ALTER TABLE agents ADD COLUMN total_earnings   DECIMAL(12,2) NOT NULL DEFAULT 0"),
                    ("tickets_claimed",  "ALTER TABLE agents ADD COLUMN tickets_claimed  INT NOT NULL DEFAULT 0"),
                    ("tickets_resolved", "ALTER TABLE agents ADD COLUMN tickets_resolved INT NOT NULL DEFAULT 0"),
                ]:
                    if not _column_exists(c, "agents", col):
                        c.execute(ddl)

            # PENDING_AGENTS
            if not _table_exists(c, "pending_agents"):
                c.execute("""
                    CREATE TABLE pending_agents (
                      id           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
                      user_id      BIGINT       NOT NULL UNIQUE,
                      full_name    VARCHAR(100)          DEFAULT NULL,
                      languages    TEXT                   DEFAULT NULL,
                      availability TEXT                   DEFAULT NULL,
                      requested_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)

            # TICKETS
            if not _table_exists(c, "tickets"):
                c.execute("""
                    CREATE TABLE tickets (
                      id                 BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
                      user_id            BIGINT       NOT NULL,
                      opened_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      closed_at          DATETIME              DEFAULT NULL,
                      resolved           TINYINT(1)   NOT NULL DEFAULT 0,
                      claimed_by         BIGINT                DEFAULT NULL,
                      first_message_link VARCHAR(255)          DEFAULT NULL,
                      last_message_link  VARCHAR(255)          DEFAULT NULL,
                      INDEX idx_ticket_user  (user_id),
                      INDEX idx_ticket_open  (closed_at),
                      INDEX idx_ticket_claim (claimed_by)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            # else: add later columns here if schema evolves

        conn.commit()
        print("✅ DB migrations ok")
    except Exception as e:
        print("❌ DB migration failed:", e)
    finally:
        conn.close()

# ------------- Language / Misc ------------- #
def save_user_language(user_id, lang_code):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET language = %s WHERE userid = %s", (lang_code, user_id))

def clear_ticket_claim(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET claimed_by = NULL WHERE userid = %s", (user_id,))

def get_claimed_ticket_by_agent(agent_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT userid FROM users WHERE claimed_by = %s AND open_ticket = 1", (agent_id,))
        row = cursor.fetchone()
        return row['userid'] if row else None

def get_agent_profile(user_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT full_name, languages, availability,
                       commission_rate, total_earnings,
                       tickets_claimed, tickets_resolved
                FROM agents WHERE user_id=%s
            """, (user_id,))
            return c.fetchone()
    finally:
        conn.close()

def increment_claim(agent_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE agents SET tickets_claimed = tickets_claimed + 1 WHERE user_id=%s", (agent_id,))
    finally:
        conn.close()

def increment_resolved_and_pay(agent_id):
    base = getattr(config, 'ticket_commission_base', 1.0)
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT commission_rate FROM agents WHERE user_id=%s", (agent_id,))
            row = c.fetchone()
            if not row:
                return
            rate = float(row['commission_rate'] or 0)
            earning = base * rate
            c.execute("""
                UPDATE agents
                   SET tickets_resolved = tickets_resolved + 1,
                       total_earnings   = total_earnings + %s
                 WHERE user_id=%s
            """, (earning, agent_id))
    finally:
        conn.close()

def set_commission(agent_id, rate):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE agents SET commission_rate=%s WHERE user_id=%s", (rate, agent_id))
    finally:
        conn.close()

def get_agent_stats(agent_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT full_name, commission_rate, total_earnings,
                       tickets_claimed, tickets_resolved
                FROM agents WHERE user_id=%s
            """, (agent_id,))
            return c.fetchone()
    finally:
        conn.close()

def get_report_summary():
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS total_tickets FROM users")
            total_tickets = c.fetchone()['total_tickets']

            c.execute("SELECT COUNT(*) AS open_now FROM users WHERE open_ticket=1")
            open_now = c.fetchone()['open_now']

            c.execute("SELECT COUNT(*) AS banned_cnt FROM users WHERE banned=1")
            banned_cnt = c.fetchone()['banned_cnt']

            c.execute("SELECT SUM(tickets_resolved) AS resolved, SUM(total_earnings) AS earned FROM agents")
            row = c.fetchone()
            resolved = row['resolved'] or 0
            earned = float(row['earned'] or 0)

            c.execute("""
                SELECT user_id, full_name, tickets_resolved
                FROM agents ORDER BY tickets_resolved DESC LIMIT 5
            """)
            top = c.fetchall()

            return {
                "total_tickets": total_tickets,
                "open_now": open_now,
                "banned_cnt": banned_cnt,
                "resolved": resolved,
                "earned": earned,
                "top": top
            }
    finally:
        conn.close()

def get_agent_languages(agent_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT languages FROM agents WHERE user_id = %s", (agent_id,))
        row = cursor.fetchone()
        if not row:
            return None
        if not row['languages']:
            return []
        return [lang.strip() for lang in row['languages'].split(',')]

def get_user_language(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT language FROM users WHERE userid = %s", (user_id,))
        row = cursor.fetchone()
        return row['language'] if row and row['language'] else 'en'

# (legacy helper kept; migrations supersede it)
def ensure_claimed_by_column():
    try:
        conn = getConnection()
        with conn.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM users LIKE 'claimed_by'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD claimed_by BIGINT DEFAULT NULL")
                print("✅ Added 'claimed_by' column to users table")
    except Exception as e:
        print("⚠️ Failed to ensure claimed_by column:", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def createTables():
    """Kept for backward compatibility (noop)."""
    return

def save_pending_agent(user_id, full_name, languages, availability):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO pending_agents (user_id, full_name, languages, availability) VALUES (%s, %s, %s, %s)",
            (user_id, full_name, languages, availability)
        )

def get_pending_agents():
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM pending_agents")
        return cursor.fetchall()

def approve_agent(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT full_name, languages, availability FROM pending_agents WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return
        cursor.execute(
            "INSERT INTO agents (user_id, full_name, languages, availability) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE full_name=VALUES(full_name), languages=VALUES(languages), availability=VALUES(availability)",
            (user_id, row['full_name'], row['languages'], row['availability'])
        )
        cursor.execute("DELETE FROM pending_agents WHERE user_id = %s", (user_id,))

def reject_agent(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM pending_agents WHERE user_id = %s", (user_id,))

# ------------- Spam / user state ------------- #
def spam(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT banned, open_ticket, open_ticket_spam FROM users WHERE userid = %s", user_id)
        data = cursor.fetchone()
        ticket_spam = data['open_ticket_spam']
        cursor.execute("UPDATE users SET open_ticket_spam = %s WHERE userid = %s", (ticket_spam + 1, user_id))
        return ticket_spam + 1

def user_tables(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT open_ticket, banned, open_ticket_time, open_ticket_spam, open_ticket_link
            FROM users WHERE userid = %s
        """, user_id)
        return cursor.fetchone()

def getOpenTickets():
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT userid FROM users WHERE open_ticket = 1")
        return [i['userid'] for i in cursor.fetchall()]

def getBanned():
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT userid FROM users WHERE banned = 1")
        return [i['userid'] for i in cursor.fetchall()]

def start_bot(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT EXISTS(SELECT userid FROM users WHERE userid = %s)", user_id)
        if not list(cursor.fetchone().values())[0]:
            cursor.execute("INSERT INTO users(userid) VALUES (%s)", user_id)

def open_ticket(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET open_ticket = 1, open_ticket_time = %s WHERE userid = %s",
                       (datetime.now(), user_id))
        if user_id not in open_tickets:
            open_tickets.append(user_id)

def post_open_ticket(link, msg_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET open_ticket_link = %s WHERE userid = %s", (link, msg_id))

def reset_open_ticket(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET open_ticket = 0, open_ticket_spam = 1 WHERE userid = %s", user_id)
        if user_id in open_tickets:
            open_tickets.remove(user_id)

def ban_user(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET banned = 1 WHERE userid = %s", user_id)
        if user_id not in banned:
            banned.append(user_id)

def unban_user(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET banned = 0 WHERE userid = %s", user_id)
        if user_id in banned:
            banned.remove(user_id)

def claim_ticket(user_id, agent_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET claimed_by = %s WHERE userid = %s", (agent_id, user_id))

def get_ticket_claim(user_id):
    conn = getConnection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT claimed_by FROM users WHERE userid = %s", (user_id,))
        row = cursor.fetchone()
        return row['claimed_by'] if row else None

# ------------- Ticket lifecycle ------------- #
def create_ticket(user_id, first_link):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""INSERT INTO tickets (user_id, first_message_link)
                         VALUES (%s, %s)""", (user_id, first_link))
            tid = c.lastrowid
            c.execute("UPDATE users SET current_ticket_id=%s WHERE userid=%s", (tid, user_id))
            return tid
    finally:
        conn.close()

def mark_ticket_last_link(ticket_id, link):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE tickets SET last_message_link=%s WHERE id=%s", (link, ticket_id))
    finally:
        conn.close()

def set_ticket_claim(ticket_id, agent_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE tickets SET claimed_by=%s WHERE id=%s", (agent_id, ticket_id))
    finally:
        conn.close()

def mark_ticket_resolved(ticket_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE tickets SET resolved=1 WHERE id=%s", (ticket_id,))
    finally:
        conn.close()

def close_ticket(ticket_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("UPDATE tickets SET closed_at=NOW() WHERE id=%s", (ticket_id,))
    finally:
        conn.close()

def get_current_ticket(user_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT t.* FROM tickets t
                JOIN users u ON u.current_ticket_id=t.id
                WHERE u.userid=%s AND t.closed_at IS NULL
            """, (user_id,))
            return c.fetchone()
    finally:
        conn.close()

def get_ticket_by_id(ticket_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("SELECT * FROM tickets WHERE id=%s", (ticket_id,))
            return c.fetchone()
    finally:
        conn.close()

def get_last_unresolved_ticket(user_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""
                SELECT * FROM tickets
                 WHERE user_id=%s AND resolved=0 AND closed_at IS NOT NULL
              ORDER BY closed_at DESC LIMIT 1
            """, (user_id,))
            return c.fetchone()
    finally:
        conn.close()

def reset_user_ticket_state(user_id):
    conn = getConnection()
    try:
        with conn.cursor() as c:
            c.execute("""
                UPDATE users
                   SET current_ticket_id=NULL,
                       open_ticket=0,
                       open_ticket_spam=1
                 WHERE userid=%s
            """, (user_id,))
    finally:
        conn.close()

# ------------- Globals ------------- #
# Call after migrations to ensure tables exist
try:
    open_tickets = getOpenTickets()
    banned = getBanned()
except Exception:
    # If called before migrations, will be re-populated after run_migrations()
    open_tickets = []
    banned = []
