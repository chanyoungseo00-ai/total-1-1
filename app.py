import streamlit as st
import pandas as pd
import numpy as np
import io
import random
import itertools
import traceback

st.set_page_config(page_title="그라운드골프 통합 시스템", layout="wide")

try:
    # ==========================================
    # [기능 1] 대진표 자동 편성 로직
    # ==========================================
    def assign_teams_and_orders(df, holes_per_field=8, players_per_team=6, match_type="개인전"):
        working_df = df.copy()
        
        working_df['성별'] = working_df['성별'].astype(str).str.strip().str[0] 
        working_df['지역'] = working_df['지역'].astype(str).str.strip()
        
        num_teams = (len(working_df) + players_per_team - 1) // players_per_team
        if num_teams == 0: 
            return pd.DataFrame(), 0, {}
        
        teams = [[] for _ in range(num_teams)]
        fields = ['청', '백', '홍', '황']
        
        if match_type == "개인전":
            players = working_df.to_dict('records')
            r_counts = working_df['지역'].value_counts().to_dict()
            players.sort(key=lambda x: (r_counts.get(x['지역'], 0), x['지역']), reverse=True)
            for p in players:
                allowed = [t for t in teams if len(t) < players_per_team]
                if not allowed: allowed = teams
                
                best_team = min(allowed, key=lambda t: (sum(1 for x in t if x['지역'] == p['지역']), len(t)))
                best_team.append(p)
                
        else: 
            females = working_df[working_df['성별'] == '여'].to_dict('records')
            males = working_df[working_df['성별'] == '남'].to_dict('records')
            
            for team in teams:
                for _ in range(2):
                    if not females: break
                    min_overlap = min(sum(1 for x in team if x['지역'] == f['지역']) for f in females)
                    for i, f in enumerate(females):
                        if sum(1 for x in team if x['지역'] == f['지역']) == min_overlap:
                            team.append(females.pop(i))
                            break
                            
            rem = females + males
            rem_counts = pd.Series([p['지역'] for p in rem]).value_counts().to_dict()
            rem.sort(key=lambda x: (rem_counts.get(x['지역'], 0), x['지역']), reverse=True)
            for p in rem:
                allowed = [t for t in teams if len(t) < players_per_team]
                if not allowed: allowed = teams
                
                best_team = min(allowed, key=lambda t: (sum(1 for x in t if x['지역'] == p['지역']), len(t)))
                best_team.append(p)

        region_order_count = {r: {i: 0 for i in range(1, players_per_team + 1)} for r in working_df['지역'].unique()}
        for team in teams:
            avail_orders = list(range(1, players_per_team + 1))
            best_perm = None
            best_score = float('inf')
            perms = [random.sample(avail_orders, len(team)) for _ in range(2000)]
            for perm in perms:
                score = 0
                for i, p in enumerate(team):
                    score += region_order_count[p['지역']].get(perm[i], 0) ** 2
                if score < best_score:
                    best_score = score
                    best_perm = perm
                    if score == 0: break
            for i, p in enumerate(team):
                p['타순'] = best_perm[i]
                region_order_count[p['지역']][best_perm[i]] += 1

        final_roster = []
        for idx, team in enumerate(teams):
            f_idx = idx % 4
            field_name = fields[f_idx]
            hole = (idx // 4) % holes_per_field + 1
            round_id = (idx // (4 * holes_per_field)) + 1
            
            s_hole = f"{field_name}구장 {hole}홀"
            set_name = f"{round_id}그룹 {field_name}구장" if len(teams) > holes_per_field * 4 else f"{field_name}구장"
                
            for p in team:
                final_roster.append({
                    '진행 그룹': set_name, '팀': f"{match_type} {idx+1}조", 
                    '구장': field_name, '홀': hole, '타순': p['타순'], 
                    '지역': p['지역'], '이름': p['이름'], '성별': p['성별'],
                    '_r': round_id, '_f': f_idx, '_h': hole
                })
                
        res_df = pd.DataFrame(final_roster).sort_values(by=['_r', '_f', '_h', '타순']).reset_index(drop=True)
        return res_df.drop(columns=['_r', '_f', '_h']), num_teams, region_order_count

    # ==========================================
    # [기능 2] 인쇄용 대진표 엑셀 출력 양식
    # ==========================================
    def create_print_excel(df, match_type, holes_cnt):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
            cell_fmt = workbook.add_format({'border': 1, 'align': 'center'})
            
            for f_name in ['청', '백', '홍', '황']:
                f_df = df[df['구장'] == f_name]
                if f_df.empty: continue
                
                worksheet = workbook.add_worksheet(f"{f_name}구장 대진표")
                worksheet.set_column('A:N', 10)
                worksheet.write(0, 0, f"제18회 대한체육회장배 {match_type} 대진표 ({f_name}구장)", workbook.add_format({'bold': True, 'font_size': 14}))
                
                row = 3
                for h in range(1, holes_cnt + 1, 2):
                    h1_data = f_df[f_df['홀'] == h]
                    h2_data = f_df[f_df['홀'] == h+1]
                    
                    heads = ['홀', '타순', '지역', '이름', '성별', '심판']
                    for c, text in enumerate(heads):
                        worksheet.write(row, c, text, header_fmt)
                        worksheet.write(row, c+7, text, header_fmt)
                    row += 1
                    
                    max_len = max(len(h1_data), len(h2_data), 6)
                    for i in range(max_len):
                        if i < len(h1_data):
                            p = h1_data.iloc[i]
                            val_h = h if i == 0 else ""
                            worksheet.write(row+i, 0, val_h, cell_fmt)
                            worksheet.write(row+i, 1, p['타순'], cell_fmt)
                            worksheet.write(row+i, 2, p['지역'], cell_fmt)
                            worksheet.write(row+i, 3, p['이름'], cell_fmt)
                            worksheet.write(row+i, 4, p['성별'], cell_fmt)
                            worksheet.write(row+i, 5, "", cell_fmt)
                        if i < len(h2_data):
                            p = h2_data.iloc[i]
                            val_h2 = h+1 if i == 0 else ""
                            worksheet.write(row+i, 7, val_h2, cell_fmt)
                            worksheet.write(row+i, 8, p['타순'], cell_fmt)
                            worksheet.write(row+i, 9, p['지역'], cell_fmt)
                            worksheet.write(row+i, 10, p['이름'], cell_fmt)
                            worksheet.write(row+i, 11, p['성별'], cell_fmt)
                            worksheet.write(row+i, 12, "", cell_fmt)
                    row += max_len + 1
        return output.getvalue()

    # ==========================================
    # [기능 3] 채점 데이터 로드 및 정규화
    # ==========================================
    def load_score_data(file, sheet_name, days):
        df = pd.read_excel(file, sheet_name=sheet_name, skiprows=2, header=None)
        cols = [
            '일시', '조', '타순', '소속', '이름', 
            '1_총', '1_2', '1_홀', 
            '2_총', '2_2', '2_홀', 
            '3_총', '3_2', '3_홀', 
            '최_총', '최_2', '최_홀'
        ]
        if days == "1일차 대회": 
            df = df.iloc[:, :11].copy()
            df.columns = cols[:8] + cols[14:17]
            df['2_총'], df['2_2'], df['2_홀'] = 0, 0, 0
            df['3_총'], df['3_2'], df['3_홀'] = 0, 0, 0
        elif days == "2일차 대회": 
            df = df.iloc[:, :14].copy()
            df.columns = cols[:11] + cols[14:17]
            df['3_총'], df['3_2'], df['3_홀'] = 0, 0, 0
        else: 
            df = df.iloc[:, :17].copy()
            df.columns = cols
            
        df = df.dropna(subset=['이름', '소속'])
        num_cols = [
            '1_총', '1_2', '1_홀', '2_총', '2_2', '2_홀', 
            '3_총', '3_2', '3_홀', '최_총', '최_2', '최_홀'
        ]
        for c in num_cols: 
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
        return df

    # ==========================================
    # [메인 화면 UI]
    # ==========================================
    st.sidebar.title("⛳ 운영 통합 시스템")
    mode = st.sidebar.radio("작업 선택", ["대진표 편성", "대회 채점"])

    if mode == "대진표 편성":
        st.title("⛳ 대진표 자동 편성")
        m_type = st.sidebar.radio("편성 부문", ["개인전", "단체전"])
        h_cnt = st.sidebar.radio("출발홀 수", [6, 7, 8], index=2)
        p_cnt = st.sidebar.radio("조당 인원", [6, 7, 8], index=0)
        
        up_file = st.file_uploader("선수 명단 엑셀 업로드", type=["xlsx"])
        
        if up_file:
            try:
                xls = pd.ExcelFile(up_file)
                sheet_names = xls.sheet_names
                selected_sheet = st.selectbox("📂 명단이 들어있는 엑셀 시트를 정확히 선택하세요", sheet_names)
                
                df_raw = pd.read_excel(up_file, sheet_name=selected_sheet, header=None)
                header_idx = 0
                for i, row in df_raw.iterrows():
                    row_str = row.astype(str).str.replace(" ", "").tolist()
                    if '이름' in row_str or '성명' in row_str:
                        header_idx = i
                        break
                        
                df_raw.columns = df_raw.iloc[header_idx].astype(str).str.strip()
                df_raw = df_raw.iloc[header_idx+1:].reset_index(drop=True)
                df_raw = df_raw.rename(columns={'소속': '지역', '성명': '이름'})
                
                if '이름' not in df_raw.columns:
                    st.error("❌ 선택하신 시트에서 [이름(또는 성명)] 열을 찾을 수 없습니다. 시트를 다시 확인해 주세요.")
                else:
                    df_raw = df_raw.dropna(subset=['이름'])
                    df_raw = df_raw[df_raw['이름'].astype(str).str.strip().str.lower() != 'nan']
                    df_raw = df_raw[df_raw['이름'].astype(str).str.strip() != '']
                    
                    if '지역' not in df_raw.columns: df_raw['지역'] = '미기재'
                    if '성별' not in df_raw.columns: df_raw['성별'] = '남'
                    
                    df_raw['지역'] = df_raw['지역'].fillna('미기재')
                    df_raw['성별'] = df_raw['성별'].fillna('남')
                    
                    df_clean = df_raw[['지역', '이름', '성별']].copy()
                    
                    st.info(f"총 **{len(df_clean)}명**의 선수 명단을 성공적으로 불러왔습니다.")
                    
                    if st.button(f"🚀 {m_type} 대진표 생성 실행"):
                        res, t_cnt, order_stats = assign_teams_and_orders(df_clean, h_cnt, p_cnt, m_type)
                        
                        st.subheader(f"✅ {m_type} 편성 완료 (총 {t_cnt}개 조)")
                        st.dataframe(res, use_container_width=True)
                        
                        if m_type == "단체전":
                            st.markdown("---")
                            st.subheader("📊 단체전 타순 순환 배치 검증 보고서")
                            order_df = pd.DataFrame(order_stats).T.fillna(0).astype(int)
                            order_df.columns = [f"{i}번 타순" for i in order_df.columns]
                            st.dataframe(order_df, use_container_width=True)
                        
                        print_excel = create_print_excel(res, m_type, h_cnt)
                        st.download_button(
                            label="📥 인쇄용 공식 대진표 다운로드", 
                            data=print_excel, 
                            file_name=f"{m_type}_최종_대진표.xlsx"
                        )
                        
            except Exception as e:
                st.error(f"엑셀 파일을 처리하는 도중 문제가 발생했습니다: {e}")

    elif mode == "대회 채점":
        st.title("🏆 대회 통합 채점 시스템")
        d_set = st.sidebar.radio("대회 일정", ["1일차 대회", "2일차 대회", "3일차 대회"])
        up_score = st.file_uploader("채점표 엑셀 업로드", type=["xlsx"])
        
        if up_score:
            t1, t2 = st.tabs(["🥇 개인전", "🤝 단체전"])
            
            with t1:
                try:
                    df_p = load_score_data(up_score, '개인전 채점표', d_set)
                    
                    df_p['최_총'] = df_p['1_총'] + df_p['2_총'] + df_p['3_총']
                    df_p['최_2'] = df_p['1_2'] + df_p['2_2'] + df_p['3_2']
                    df_p['최_홀'] = df_p['1_홀'] + df_p['2_홀'] + df_p['3_홀']
                    
                    df_p = df_p.sort_values(
                        by=['최_총','최_2','최_홀'], 
                        ascending=[True,False,False]
                    ).reset_index(drop=True)
                    
                    df_p['순위'] = df_p[['최_총','최_2','최_홀']].apply(
                        lambda x: (-x['최_총'], x['최_2'], x['최_홀']), axis=1
                    ).rank(method='min', ascending=False).astype(int)
                    
                    st.subheader(f"🥇 개인전 순위표 ({d_set})")
                    display_cols_p = ['순위', '소속', '이름', '최_총', '최_2', '최_홀']
                    st.dataframe(df_p[display_cols_p], hide_index=True)
                except Exception as e: 
                    st.error(f"개인전 시트에서 오류가 발생했습니다: {e}")
                    
            with t2:
                try:
                    df_t = load_score_data(up_score, '단체전 채점표', d_set)
                    
                    df_t['최_총'] = df_t['1_총'] + df_t['2_총'] + df_t['3_총']
                    df_t['최_2'] = df_t['1_2'] + df_t['2_2'] + df_t['3_2']
                    df_t['최_홀'] = df_t['1_홀'] + df_t['2_홀'] + df_t['3_홀']
                    
                    res_t = df_t.groupby('소속', as_index=False)[['최_총','최_2','최_홀']].sum()
                    
                    res_t = res_t.sort_values(
                        by=['최_총','최_2','최_홀'], 
                        ascending=[True,False,False]
                    ).reset_index(drop=True)
                    
                    res_t['순위'] = res_t[['최_총','최_2','최_홀']].apply(
                        lambda x: (-x['최_총'], x['최_2'], x['최_홀']), axis=1
                    ).rank(method='min', ascending=False).astype(int)
                    
                    st.subheader(f"🤝 단체전 순위표 ({d_set})")
                    display_cols_t = ['순위', '소속', '최_총', '최_2', '최_홀']
                    st.dataframe(res_t[display_cols_t], hide_index=True)
                except Exception as e: 
                    st.error(f"단체전 시트에서 오류가 발생했습니다: {e}")
            
            if 'df_p' in locals() or 'res_t' in locals():
                st.markdown("---")
                out_score = io.BytesIO()
                with pd.ExcelWriter(out_score, engine='xlsxwriter') as wr:
                    if 'df_p' in locals(): 
                        df_p.to_excel(wr, index=False, sheet_name='개인전_최종결과')
                    if 'res_t' in locals(): 
                        res_t.to_excel(wr, index=False, sheet_name='단체전_최종결과')
                        
                st.download_button(
                    label=f"📥 {d_set} 최종 채점 결과 다운로드", 
                    data=out_score.getvalue(), 
                    file_name=f"최종_채점결과({d_set}).xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

except Exception as e:
    st.error(f"🚨 프로그램 구동 중 치명적인 에러가 발생했습니다: {e}")
    st.code(traceback.format_exc())