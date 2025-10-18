import streamlit as st
import pandas as pd
from pymongo import MongoClient
import bcrypt
import os
from datetime import datetime

# --- MongoDB Connection ---
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["splitwise_clone"]
users_col = db["users"]
groups_col = db["groups"]
expenses_col = db["expenses"]

# --- Helpers ---
def create_user(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    users_col.insert_one({"username": username, "password_hash": hashed})

def check_user(username, password):
    user = users_col.find_one({"username": username})
    if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
        return user
    return None

def create_group(name, owner_id):
    groups_col.insert_one({"name": name, "owner_id": owner_id, "members": [owner_id]})

def get_groups(user_id):
    return list(groups_col.find({"members": {"$in": [user_id]}}))

def add_member(group_id, member_name):
    groups_col.update_one({"_id": group_id}, {"$addToSet": {"members": member_name}})

def add_expense(group_id, desc, amount, paid_by, split_between):
    expenses_col.insert_one({
        "group_id": group_id,
        "description": desc,
        "amount": float(amount),
        "paid_by": paid_by,
        "split_between": split_between,
        "created_at": datetime.utcnow()
    })

def get_expenses(group_id):
    return list(expenses_col.find({"group_id": group_id}))

def compute_balances(group_id):
    group = groups_col.find_one({"_id": group_id})
    members = group["members"]
    balances = {m: 0 for m in members}
    expenses = get_expenses(group_id)

    for e in expenses:
        amount = e["amount"]
        payer = e["paid_by"]
        split = e["split_between"]
        share = amount / len(split)
        for m in split:
            if m != payer:
                balances[m] -= share
                balances[payer] += share
    return balances

# --- Streamlit UI ---
st.set_page_config(page_title="Splitwise Clone MongoDB", page_icon="💸")
st.title("💸 Splitwise Clone (MongoDB Version)")

# Session state
if "user" not in st.session_state:
    st.session_state.user = None

# Auth
if st.session_state.user is None:
    tab1, tab2 = st.tabs(["Sign In", "Sign Up"])

    with tab1:
        username = st.text_input("Username", key="signin_user")
        password = st.text_input("Password", type="password", key="signin_pass")
        if st.button("Sign In"):
            user = check_user(username, password)
            if user:
                st.session_state.user = username
                st.success(f"Welcome, {username}")
                st.experimental_rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        new_user = st.text_input("New Username", key="signup_user")
        new_pass = st.text_input("New Password", type="password", key="signup_pass")
        if st.button("Sign Up"):
            if users_col.find_one({"username": new_user}):
                st.error("Username already exists")
            else:
                create_user(new_user, new_pass)
                st.success("Account created! You can sign in now.")

else:
    username = st.session_state.user
    st.sidebar.success(f"Logged in as {username}")
    if st.sidebar.button("Log Out"):
        st.session_state.user = None
        st.experimental_rerun()

    # Groups
    st.header("Groups")
    groups = get_groups(username)
    group_names = [g["name"] for g in groups]

    selected = st.selectbox("Select a group", ["-- New Group --"] + group_names)

    if selected == "-- New Group --":
        new_name = st.text_input("New Group Name")
        if st.button("Create Group"):
            create_group(new_name, username)
            st.success("Group created")
            st.experimental_rerun()
    else:
        group = next(g for g in groups if g["name"] == selected)
        group_id = group["_id"]

        st.subheader(f"Group: {selected}")

        # Add members
        st.write("### Members")
        members = group["members"]
        st.write(", ".join(members))
        new_member = st.text_input("Add member name")
        if st.button("Add Member"):
            if new_member not in members:
                add_member(group_id, new_member)
                st.success("Member added")
                st.experimental_rerun()

        # Add expense
        st.write("### Add Expense")
        desc = st.text_input("Description")
        amount = st.number_input("Amount (€)", min_value=0.0, step=0.01)
        paid_by = st.selectbox("Paid by", members)
        split_between = st.multiselect("Split between", members, default=members)
        if st.button("Add Expense"):
            add_expense(group_id, desc, amount, paid_by, split_between)
            st.success("Expense added")
            st.experimental_rerun()

        # Expense history
        st.write("### Expense History")
        exps = get_expenses(group_id)
        if exps:
            st.dataframe(pd.DataFrame(exps)[["description","paid_by","amount","split_between","created_at"]])
        else:
            st.info("No expenses yet")

        # Balances
        st.write("### Balances")
        balances = compute_balances(group_id)
        for person, bal in balances.items():
            if bal > 0:
                st.success(f"{person} should receive €{bal:.2f}")
            elif bal < 0:
                st.error(f"{person} owes €{-bal:.2f}")
            else:
                st.info(f"{person} is settled ✅")
