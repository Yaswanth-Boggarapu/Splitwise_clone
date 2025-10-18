import streamlit as st
import pandas as pd
import pymysql
import bcrypt
import os

# --- DB Connection ---
def get_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DB"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        cursorclass=pymysql.cursors.DictCursor
    )

# --- Helper functions ---
def create_user(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed))
        conn.commit()
    conn.close()

def check_user(username, password):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
    conn.close()
    if not user:
        return None
    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return user
    return None

def create_group(name, owner_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (name, owner_id) VALUES (%s, %s)", (name, owner_id))
        conn.commit()
    conn.close()

def get_groups(user_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM groups WHERE owner_id=%s", (user_id,))
        groups = cur.fetchall()
    conn.close()
    return groups

def add_member(group_id, member_name):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO group_members (group_id, member_name) VALUES (%s, %s)", (group_id, member_name))
        conn.commit()
    conn.close()

def get_members(group_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM group_members WHERE group_id=%s", (group_id,))
        members = cur.fetchall()
    conn.close()
    return [m["member_name"] for m in members]

def add_expense(group_id, desc, amount, paid_by, split_between):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO expenses (group_id, description, amount, paid_by, split_between) VALUES (%s,%s,%s,%s,%s)",
                    (group_id, desc, amount, paid_by, ",".join(split_between)))
        conn.commit()
    conn.close()

def get_expenses(group_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM expenses WHERE group_id=%s", (group_id,))
        exps = cur.fetchall()
    conn.close()
    return exps

def compute_balances(group_id):
    members = get_members(group_id)
    balances = {m: 0 for m in members}
    expenses = get_expenses(group_id)

    for e in expenses:
        amount = e["amount"]
        payer = e["paid_by"]
        split_between = e["split_between"].split(",")
        share = amount / len(split_between)
        for m in split_between:
            if m != payer:
                balances[m] -= share
                balances[payer] += share
    return balances

# --- UI ---
st.set_page_config(page_title="Splitwise Clone", page_icon="💸")
st.title("💸 Splitwise Clone (Free Version)")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None

# Auth section
if st.session_state.user is None:
    tab1, tab2 = st.tabs(["Sign In", "Sign Up"])

    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Sign In"):
            user = check_user(username, password)
            if user:
                st.session_state.user = user
                st.success(f"Welcome, {username}")
                st.experimental_rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            try:
                create_user(new_user, new_pass)
                st.success("Account created! You can now log in.")
            except Exception as e:
                st.error(f"Error: {e}")

else:
    user = st.session_state.user
    st.sidebar.success(f"Logged in as {user['username']}")
    if st.sidebar.button("Log Out"):
        st.session_state.user = None
        st.experimental_rerun()

    # Groups section
    st.header("Groups")
    groups = get_groups(user["id"])
    group_names = [g["name"] for g in groups]

    selected = st.selectbox("Select a group", ["-- New Group --"] + group_names)

    if selected == "-- New Group --":
        new_name = st.text_input("New Group Name")
        if st.button("Create Group"):
            create_group(new_name, user["id"])
            st.success("Group created.")
            st.experimental_rerun()
    else:
        group = next(g for g in groups if g["name"] == selected)
        group_id = group["id"]

        st.subheader(f"Group: {selected}")

        # Add members
        st.write("### Members")
        members = get_members(group_id)
        st.write(", ".join(members) if members else "No members yet.")
        new_member = st.text_input("Add member name")
        if st.button("Add Member"):
            add_member(group_id, new_member)
            st.success("Member added.")
            st.experimental_rerun()

        # Add expense
        st.write("### Add Expense")
        desc = st.text_input("Description")
        amount = st.number_input("Amount (€)", min_value=0.0, step=0.01)
        paid_by = st.selectbox("Paid by", members if members else ["(add members first)"])
        split_between = st.multiselect("Split between", members, default=members)
        if st.button("Add Expense"):
            add_expense(group_id, desc, amount, paid_by, split_between)
            st.success("Expense added.")

        # Expense table
        st.write("### Expense History")
        exps = get_expenses(group_id)
        if exps:
            st.dataframe(pd.DataFrame(exps)[["description", "paid_by", "amount", "split_between", "created_at"]])
        else:
            st.info("No expenses yet.")

        # Balances
        st.write("### Balances")
        balances = compute_balances(group_id)
        for person, bal in balances.items():
            if bal > 0:
                st.success(f"{person} should receive €{bal:.2f}")
            elif bal < 0:
                st.error(f"{person} owes €{-bal:.2f}")
            else:
                st.info(f"{person} is settled up ✅")
