import streamlit as st
import pandas as pd
import sqlite3
import os
import requests
import json
from datetime import datetime

st.set_page_config(page_title="邵阳商会出海智能体", layout="wide")
st.title("🤖 邵阳商会出海智能体")

def init_db():
    conn = sqlite3.connect('members.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS members
                 (id INTEGER PRIMARY KEY,
                  name TEXT,
                  tags TEXT,
                  countries TEXT,
                  services TEXT,
                  contact TEXT,
                  phone TEXT,
                  raw_text TEXT,
                  source_file TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS demands
                 (id INTEGER PRIMARY KEY,
                  question TEXT,
                  keywords TEXT,
                  create_time TEXT,
                  status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def auto_map_columns(df):
    col_map = {}
    lower_cols = {str(c).lower(): c for c in df.columns}
    for kw in ['企业名称', '公司名', 'name', 'company']:
        if kw in lower_cols:
            col_map['name'] = lower_cols[kw]
            break
    for kw in ['业务标签', '标签', 'tags']:
        if kw in lower_cols:
            col_map['tags'] = lower_cols[kw]
            break
    for kw in ['擅长国家', '国家', 'countries']:
        if kw in lower_cols:
            col_map['countries'] = lower_cols[kw]
            break
    for kw in ['可提供服务', '服务', 'services']:
        if kw in lower_cols:
            col_map['services'] = lower_cols[kw]
            break
    for kw in ['联系人', '姓名', 'contact']:
        if kw in lower_cols:
            col_map['contact'] = lower_cols[kw]
            break
    for kw in ['电话', '手机', '联系电话', 'phone', 'mobile']:
        if kw in lower_cols:
            col_map['phone'] = lower_cols[kw]
            break
    return col_map

def clean_phone(phone):
    phone_str = str(phone).strip()
    if phone_str.endswith('.0'):
        phone_str = phone_str[:-2]
    return phone_str

def call_llm(prompt):
    api_key = "sk-hN6uiAS3igw6LpcxcmH6ynZFFKqS1N44VdnQAispjqlyonhX"
    url = "https://api.meai.cloud/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": "deepseek-v4", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        return resp.json()["choices"][0]["message"]["content"]
    except:
        return ""

def match_members(question):
    conn = sqlite3.connect('members.db')
    df = pd.read_sql("SELECT * FROM members", conn)
    conn.close()
    if len(df) == 0:
        return [], False
    
    enterprises_text = ""
    for _, row in df.iterrows():
        enterprises_text += f"- {row['name']} | 业务：{row['tags']} | 国家：{row['countries']} | 服务：{row['services']}\n"
    
    prompt = f"""用户需求：{question}
请从以下企业中选择最适合的1-3家，按推荐顺序输出企业名称（每行一个）。
注意理解用户需求与业务的关联，例如：
- 用户需要“代收货款” → 匹配“跨境支付”企业
- 用户需要“找律师” → 匹配“法律服务”企业
- 用户需要“废旧布料” → 匹配“布料、服装”企业

企业列表：
{enterprises_text}
只输出企业名称，不要解释。
"""
    result = call_llm(prompt)
    
    ranked_names = []
    if result:
        for line in result.strip().split('\n'):
            name = line.strip()
            if name and name[0].isdigit() and '.' in name:
                name = name.split('.', 1)[1].strip()
            if name:
                ranked_names.append(name)
    
    matches = []
    for name in ranked_names:
        for _, row in df.iterrows():
            if row['name'] == name:
                matches.append({
                    'name': row['name'],
                    'tags': row['tags'],
                    'countries': row['countries'],
                    'services': row['services'],
                    'contact': row['contact'],
                    'phone': row.get('phone', '')
                })
                break
    
    if not matches:
        payment_keywords = ['支付', '代收', '收款', '货款', '跨境支付']
        for _, row in df.iterrows():
            full_text = f"{row['tags']} {row['services']}".lower()
            for kw in payment_keywords:
                if kw in full_text:
                    matches.append({
                        'name': row['name'],
                        'tags': row['tags'],
                        'countries': row['countries'],
                        'services': row['services'],
                        'contact': row['contact'],
                        'phone': row.get('phone', '')
                    })
                    break
            if len(matches) >= 3:
                break
        
        if not matches:
            for _, row in df.iterrows():
                if '布' in row['tags'] or '服装' in row['tags']:
                    matches.append({
                        'name': row['name'],
                        'tags': row['tags'],
                        'countries': row['countries'],
                        'services': row['services'],
                        'contact': row['contact'],
                        'phone': row.get('phone', '')
                    })
                    break
    
    if not matches:
        save_demand(question)
        return [], False
    
    return matches[:5], True

def save_demand(question):
    conn = sqlite3.connect('members.db')
    conn.execute(
        "INSERT INTO demands (question, keywords, create_time, status) VALUES (?,?,?,?)",
        (question, '', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "待处理")
    )
    conn.commit()
    conn.close()

with st.sidebar:
    st.header("📁 上传资料")
    uploaded_file = st.file_uploader("上传 Excel 文件", type=['xlsx', 'xls'])
    if uploaded_file:
        df_new = pd.read_excel(uploaded_file)
        st.success(f"已读取 {len(df_new)} 条数据")
        col_map = auto_map_columns(df_new)
        
        conn = sqlite3.connect('members.db')
        conn.execute("DELETE FROM members")
        conn.commit()
        
        for _, row in df_new.iterrows():
            name = str(row.get(col_map.get('name', ''), '')) if 'name' in col_map else ''
            tags = str(row.get(col_map.get('tags', ''), '')) if 'tags' in col_map else ''
            countries = str(row.get(col_map.get('countries', ''), '')) if 'countries' in col_map else ''
            services = str(row.get(col_map.get('services', ''), '')) if 'services' in col_map else ''
            contact = str(row.get(col_map.get('contact', ''), '')) if 'contact' in col_map else ''
            phone_raw = str(row.get(col_map.get('phone', ''), '')) if 'phone' in col_map else ''
            phone = clean_phone(phone_raw)
            conn.execute(
                "INSERT INTO members (name, tags, countries, services, contact, phone, source_file) VALUES (?,?,?,?,?,?,?)",
                (name, tags, countries, services, contact, phone, uploaded_file.name)
            )
        conn.commit()
        conn.close()
        st.success(f"已吸收 {len(df_new)} 条企业信息")
    
    st.header("当前能力库")
    conn = sqlite3.connect('members.db')
    df_db = pd.read_sql("SELECT name, tags, countries, services, contact, phone FROM members", conn)
    conn.close()
    if len(df_db) > 0:
        st.dataframe(df_db)
    
    st.header("📋 待处理需求")
    conn = sqlite3.connect('members.db')
    df_demands = pd.read_sql("SELECT id, question, create_time, status FROM demands WHERE status='待处理' ORDER BY id DESC LIMIT 10", conn)
    conn.close()
    if len(df_demands) > 0:
        st.dataframe(df_demands)

question = st.text_area("请输入您的出海难题", height=100)
if st.button("智能匹配", type="primary"):
    if not question:
        st.warning("请输入问题")
    else:
        matches, has_match = match_members(question)
        if has_match:
            for m in matches:
                st.markdown(f"### {m['name']}")
                st.markdown(f"业务：{m['tags']}")
                st.markdown(f"国家：{m['countries']}")
                st.markdown(f"服务：{m['services']}")
                st.markdown(f"联系人：{m['contact']} | 电话：{m['phone']}")
                st.divider()
        else:
            st.info("📝 当前数据库中暂无匹配的企业，您的需求已记录。商会管理员会看到并为您寻找资源，同时欢迎更多相关企业加入。")
