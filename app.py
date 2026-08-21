import streamlit as st
import pandas as pd
import numpy as np
import io
import traceback

st.set_page_config(page_title="그라운드골프 대진표 시스템", layout="wide")

# ==========================================
# [모듈 1] 데이터 스캔 및 정제 엔진
# ==========================================
def process_raw_data(df_raw, default_category):
    if df_raw is None or df_raw.empty: return None, "데이터가 비어있습니다."
    
    header_idx = next((i for i, r in df_raw.iterrows() if any(x in ''.join(map(str, r)) for x in ['이름', '성명', '선수명'])), -1)
    if header_idx == -1: return None, "❌ 명단에서 [이름] 또는 [성명] 항목을 찾을 수 없습니다."
    
    df_raw.columns = df_raw.iloc[header_idx].astype(str).str.replace(r"\s+", "", regex=True)
    df_raw = df_raw.iloc[header_idx+1:].loc[:, ~df_raw.columns.duplicated()].reset_index(drop=True)
    
    rename_map = {'성명':'이름', '선수명':'이름', '소속':'지역', '시군구':'지역', '클럽':'지역', '남여':'성별'}
    df_raw.rename(columns=rename_map, inplace=True)
    
    if '이름' not in df_raw.columns or '지역' not in df_raw.columns:
        return None, "❌ 명단에 [이름]과 [지역] 열이 모두 필요합니다."
    
    for col in ['지역', '이름']:
        df_raw[col] = df_raw[col].astype(str).str.strip().replace(r'^\s*$', np.nan, regex=True).replace(['nan', 'None', 'NaN'], np.nan)
    df_clean = df_raw.dropna(subset=['지역', '이름']).copy()
    
    df_clean['성별'] = df_clean.get('성별', '남').fillna('남').astype(str).str.strip().str[0].apply(lambda x: '여' if x == '여' else '남')
    df_clean['부문'] = default_category
    df_clean['_original_idx'] = range(len(df_clean))
    
    return df_clean[['지역', '이름', '성별', '부문', '_original_idx']], ""

# ==========================================
# [모듈 2] 대진표 편성 엔진
# ==========================================
def assign_teams_and_orders(df, holes_per_field=8, p_cnt_indiv=6, p_cnt_team=6, max_rounds=3):
    players = df.to_dict('records')
    team_players = [p for p in players if '단체' in p.get('부문', '')]
    indiv_players = [p for p in players if '단체' not in p.get('부문', '')]
    
    t_req = (len(team_players) + p_cnt_team - 1) // p_cnt_team if team_players else 0
    i_req = (len(indiv_players) + p_cnt_indiv - 1) // p_cnt_indiv if indiv_players else 0
    max_limit = holes_per_field * 4 * max_rounds
    
    if t_req + i_req > max_limit:
        st.warning(f"⚠️ 인원이 초과되어 총 **{max_limit}조** 제한에 맞추어 조당 인원이 자동으로 확장(압축)되었습니다.")
        if t_req >= max_limit:
            total_p = len(team_players) + len(indiv_players)
            t_req = int(max_limit * len(team_players) / total_p)
            i_req = max_limit - t_req
        else:
            i_req = max_limit - t_req
            
        if t_req == 0 and len(team_players) > 0: t_req = 1; i_req -= 1
        if i_req == 0 and len(indiv_players) > 0: i_req = 1; t_req -= 1

    team_teams = [[] for _ in range(t_req)]
    indiv_teams = [[] for _ in range(i_req)]
    
    def distribute_players(target_players, target_teams):
        if not target_players or not target_teams: return
        p_limit = (len(target_players) + len(target_teams) - 1) // len(target_teams)
        r_counts = pd.Series([p['지역'] for p in target_players]).value_counts().to_dict()
        target_players.sort(key=lambda x: (r_counts.get(x['지역'], 0), x['지역']), reverse=True)
        for p in target_players:
            allowed = [t for t in target_teams if len(t) < p_limit] or target_teams
            best_team = min(allowed, key=lambda t: (sum(1 for x in t if x['이름'] == p['이름']), sum(1 for x in t if x['지역'] == p['지역']), sum(1 for x in t if x['성별'] == p['성별']), len(t)))
            best_team.append(p)

    def assign_orders(target_teams):
        if not target_teams: return
        region_order_count = {r: {i: 0 for i in range(1, 20)} for r in df['지역'].unique()}
        for team in target_teams:
            avail_orders = list(range(1, len(team) + 1))
            team.sort(key=lambda x: x['지역'])
            for p in team:
                best_order = min(avail_orders, key=lambda o: region_order_count[p['지역']].get(o, 0))
                p['타순'] = best_order
                avail_orders.remove(best_order)
                region_order_count[p['지역']][best_order] += 1
                
    distribute_players(team_players, team_teams)
    distribute_players(indiv_players, indiv_teams)
    assign_orders(team_teams)
    assign_orders(indiv_teams)
    
    teams = team_teams + indiv_teams
    fields = ['청', '백', '홍', '황']
    final_roster = []
    
    for idx, team in enumerate(teams):
        round_id = (idx // (holes_per_field * 4)) + 1
        idx_in_round = idx % (holes_per_field * 4)
        field_idx = idx_in_round // holes_per_field
        field_name = fields[field_idx]
        hole = (idx_in_round % holes_per_field) + 1
        
        for p in team:
            final_roster.append({
                '경기': f"{round_id}부", '구장': field_name, '홀': hole, '팀': f"{idx+1}조", 
                '타순': p['타순'], '대진표': f"{field_name} {hole} {p['타순']}",
                '부문': p['부문'], '지역': p['지역'], '이름': p['이름'], '성별': p['성별'],
                '_r': round_id, '_f': field_idx, '_h': hole, '_original_idx': p['_original_idx']
            })
            
    res_df = pd.DataFrame(final_roster).sort_values(by=['_r', '_f', '_h', '타순']).reset_index(drop=True)
    return res_df.drop(columns=['_r', '_f', '_h']), len(teams), max_limit

# ==========================================
# [모듈 3] 인쇄용 대진표 엑셀 출력
# ==========================================
def create_print_excel(df, holes_cnt):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        head_fmt = wb.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
        cell_fmt = wb.add_format({'border': 1, 'align': 'center'})
        
        for r_name in sorted(df['경기'].unique()):
            r_df = df[df['경기'] == r_name]
            for f_name in ['청', '백', '홍', '황']:
                f_df = r_df[r_df['구장'] == f_name]
                if f_df.empty: continue
                
                ws = wb.add_worksheet(f"{r_name}_{f_name}구장")
                ws.set_column('A:O', 11)
                ws.write(0, 0, f"제18회 대한체육회장배 대진표 ({r_name} {f_name}구장)", wb.add_format({'bold': True, 'font_size': 14}))
                
                row = 3
                for h in range(1, holes_cnt + 1, 2):
                    h1_data, h2_data = f_df[f_df['홀'] == h], f_df[f_df['홀'] == h+1]
                    heads = ['홀', '타순', '부문', '지역', '이름', '성별', '심판']
                    
                    for c, text in enumerate(heads):
                        ws.write(row, c, text, head_fmt)
                        ws.write(row, c+8, text, head_fmt)
                    row += 1
                    
                    for i in range(max(len(h1_data), len(h2_data), 6)):
                        if i < len(h1_data):
                            p = h1_data.iloc[i]
                            ws.write_row(row+i, 0, [h if i==0 else "", p['타순'], p['부문'], p['지역'], p['이름'], p['성별'], ""], cell_fmt)
                        if i < len(h2_data):
                            p = h2_data.iloc[i]
                            ws.write_row(row+i, 8, [h+1 if i==0 else "", p['타순'], p['부문'], p['지역'], p['이름'], p['성별'], ""], cell_fmt)
                    row += max(len(h1_data), len(h2_data), 6) + 1
    return output.getvalue()

# ==========================================
# 💡 [모듈 4] 수식 자동화 채점표 & 다중조건 완벽 순위표
# ==========================================
def create_scoring_sheet_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        head_fmt = wb.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        cell_fmt = wb.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        num_fmt = wb.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'num_format': '0'})
        rank_fmt = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#FFF2CC'})
        
        for match_type in ['단체', '개인']:
            sub_df = df[df['부문'].str.contains(match_type, na=False)].copy()
            if sub_df.empty: continue
            
            # --- 1. 심판용 채점표 시트 생성 ---
            sub_df['team_num'] = sub_df['팀'].str.extract(r'(\d+)').astype(int)
            sub_df = sub_df.sort_values(by=['team_num', '타순'])
            
            sheet_score = f"{match_type}전 채점표"
            ws = wb.add_worksheet(sheet_score)
            ws.set_column('A:A', 14)
            ws.set_column('B:C', 6)
            ws.set_column('D:E', 12)
            ws.set_column('F:N', 8)
            
            ws.merge_range('A1:A2', '일시(경기)', head_fmt)
            ws.merge_range('B1:B2', '조', head_fmt)
            ws.merge_range('C1:C2', '타순', head_fmt)
            ws.merge_range('D1:D2', '소속', head_fmt)
            ws.merge_range('E1:E2', '성명', head_fmt)
            ws.merge_range('F1:H1', '1차전', head_fmt)
            ws.merge_range('I1:K1', '2차전', head_fmt)
            ws.merge_range('L1:N1', '계', head_fmt)
            
            for col_start in [5, 8, 11]:
                ws.write(1, col_start, '총타수', head_fmt)
                ws.write(1, col_start+1, '2타수', head_fmt)
                ws.write(1, col_start+2, '홀인원', head_fmt)
                
            row = 2
            current_team = None
            for _, p in sub_df.iterrows():
                t_num = p['team_num']
                if t_num != current_team:
                    match_info = f"{p['경기']} {p['구장']}{p['홀']}홀"
                    ws.write(row, 0, match_info, cell_fmt)
                    ws.write(row, 1, t_num, cell_fmt)
                    current_team = t_num
                else:
                    ws.write(row, 0, "", cell_fmt)
                    ws.write(row, 1, "", cell_fmt)
                
                ws.write(row, 2, p['타순'], cell_fmt)
                ws.write(row, 3, p['지역'], cell_fmt)
                ws.write(row, 4, p['이름'], cell_fmt)
                
                for c in range(5, 11):
                    ws.write(row, c, "", num_fmt)
                    
                erow = row + 1 
                ws.write_formula(row, 11, f'=IF(COUNT(F{erow},I{erow})>0, SUM(F{erow},I{erow}), "")', num_fmt)
                ws.write_formula(row, 12, f'=IF(COUNT(G{erow},J{erow})>0, SUM(G{erow},J{erow}), "")', num_fmt)
                ws.write_formula(row, 13, f'=IF(COUNT(H{erow},K{erow})>0, SUM(H{erow},K{erow}), "")', num_fmt)
                row += 1
            
            # --- 2. 본부석 다중조건 완벽 순위표 시트 생성 ---
            sheet_rank = f"{match_type}전 순위표"
            ws_rank = wb.add_worksheet(sheet_rank)
            
            if match_type == '단체':
                ws_rank.set_column('A:A', 10)
                ws_rank.set_column('B:B', 18)
                ws_rank.set_column('C:E', 12)
                
                heads = ['순위', '소속', '총타수', '2타수', '홀인원']
                for c, text in enumerate(heads):
                    ws_rank.write(0, c, text, head_fmt)
                
                unique_regions = sorted(sub_df['지역'].unique())
                max_row = len(unique_regions) + 1
                
                for r_idx, region in enumerate(unique_regions, start=1):
                    erow = r_idx + 1
                    ws_rank.write(r_idx, 1, region, cell_fmt)
                    
                    ws_rank.write_formula(r_idx, 2, f"=SUMIF('{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$L:$L)", num_fmt)
                    ws_rank.write_formula(r_idx, 3, f"=SUMIF('{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$M:$M)", num_fmt)
                    ws_rank.write_formula(r_idx, 4, f"=SUMIF('{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$N:$N)", num_fmt)
                    
                    # 💡 [초강력 수식] 동타 발생 시 완벽 처리 (1순위: 총타수 적은자 / 2순위: 홀인원 많은자 / 3순위: 2타수 많은자)
                    # C열: 총타수, D열: 2타수, E열: 홀인원
                    multi_condition_formula = (
                        f'=IF(C{erow}=0, "", 1 + COUNTIFS($C$2:$C${max_row}, "<"&C{erow}) '
                        f'+ COUNTIFS($C$2:$C${max_row}, C{erow}, $E$2:$E${max_row}, ">"&E{erow}) '
                        f'+ COUNTIFS($C$2:$C${max_row}, C{erow}, $E$2:$E${max_row}, E{erow}, $D$2:$D${max_row}, ">"&D{erow}))'
                    )
                    ws_rank.write_formula(r_idx, 0, multi_condition_formula, rank_fmt)

            else:
                ws_rank.set_column('A:A', 10)
                ws_rank.set_column('B:C', 15)
                ws_rank.set_column('D:F', 12)
                
                heads = ['순위', '소속', '성명', '총타수', '2타수', '홀인원']
                for c, text in enumerate(heads):
                    ws_rank.write(0, c, text, head_fmt)
                
                sorted_sub = sub_df.sort_values(by=['지역', '이름']).reset_index(drop=True)
                max_row = len(sorted_sub) + 1
                
                for r_idx, p in enumerate(sorted_sub.itertuples(), start=1):
                    erow = r_idx + 1
                    ws_rank.write(r_idx, 1, p.지역, cell_fmt)
                    ws_rank.write(r_idx, 2, p.이름, cell_fmt)
                    
                    ws_rank.write_formula(r_idx, 3, f"=SUMIFS('{sheet_score}'!$L:$L, '{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$E:$E, C{erow})", num_fmt)
                    ws_rank.write_formula(r_idx, 4, f"=SUMIFS('{sheet_score}'!$M:$M, '{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$E:$E, C{erow})", num_fmt)
                    ws_rank.write_formula(r_idx, 5, f"=SUMIFS('{sheet_score}'!$N:$N, '{sheet_score}'!$D:$D, B{erow}, '{sheet_score}'!$E:$E, C{erow})", num_fmt)
                    
                    # 💡 [초강력 수식] 동타 발생 시 완벽 처리
                    # D열: 총타수, E열: 2타수, F열: 홀인원
                    multi_condition_formula = (
                        f'=IF(D{erow}=0, "", 1 + COUNTIFS($D$2:$D${max_row}, "<"&D{erow}) '
                        f'+ COUNTIFS($D$2:$D${max_row}, D{erow}, $F$2:$F${max_row}, ">"&F{erow}) '
                        f'+ COUNTIFS($D$2:$D${max_row}, D{erow}, $F$2:$F${max_row}, F{erow}, $E$2:$E${max_row}, ">"&E{erow}))'
                    )
                    ws_rank.write_formula(r_idx, 0, multi_condition_formula, rank_fmt)
                    
    return output.getvalue()

# ==========================================
# [모듈 5] UI 파일 입력 도우미
# ==========================================
def load_data_ui(label, source_type):
    df_raw = None
    if source_type == "엑셀 파일 업로드":
        up_file = st.file_uploader(f"📂 [{label}] 명단 엑셀 업로드", type=["xlsx"], key=f"file_{label}")
        if up_file:
            try:
                xls = pd.ExcelFile(up_file)
                sheet = st.selectbox(f"📋 [{label}] 시트 선택", xls.sheet_names, key=f"sheet_{label}")
                df_raw = pd.read_excel(up_file, sheet_name=sheet, header=None)
            except Exception as e:
                st.error(f"엑셀 파일 읽기 오류: {e}")
                
    elif source_type == "구글 시트 링크 연결":
        url = st.text_input(f"🔗 [{label}] 구글 시트 링크", key=f"url_{label}")
        if url and "/d/" in url:
            try:
                doc_id = url.split("/d/")[1].split("/")[0]
                gid = url.split("gid=")[1].split("&")[0] if "gid=" in url else "0"
                df_raw = pd.read_csv(f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&gid={gid}", header=None)
                st.success(f"✅ [{label}] 구글 시트 로드 성공!")
            except Exception as e:
                st.error(f"❌ 구글 시트 로드 실패: {e}")
    return df_raw

# ==========================================
# [메인 화면 실행부]
# ==========================================
try:
    st.title("⛳ 그라운드골프 통합 대회운영 시스템")
    
    st.sidebar.title("⚙️ 편성 설정")
    match_format = st.sidebar.radio("경기 방식 선택", ["8홀 3부 경기", "6홀 4부 경기"])
    
    if match_format == "8홀 3부 경기":
        h_cnt = 8
        max_r = 3
    else:
        h_cnt = 6
        max_r = 4

    p_cnt_team = st.sidebar.radio("단체전 조당 기본 인원", [6, 7, 8], index=0)
    p_cnt_indiv = st.sidebar.radio("개인전 조당 기본 인원", [6, 7, 8], index=0)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 데이터 입력 방식")
    data_source = st.sidebar.radio("명단 가져오기 방식", ["엑셀 파일 업로드", "구글 시트 링크 연결"])
    
    df_clean = None
    
    st.info(f"💡 **단체전 명단**과 **개인전 명단**을 각각 입력해 주세요. (구장별로 순차적으로 채워나가며, **[{match_format}]**에 따라 제한됩니다.)")
    col1, col2 = st.columns(2)
    with col1: df_raw_team = load_data_ui("단체전", data_source)
    with col2: df_raw_indiv = load_data_ui("개인전", data_source)
    
    if df_raw_team is not None and df_raw_indiv is not None:
        clean_t, err_t = process_raw_data(df_raw_team, "단체전")
        clean_i, err_i = process_raw_data(df_raw_indiv, "개인전")
        if err_t: st.error(err_t)
        elif err_i: st.error(err_i)
        else: 
            clean_i['_original_idx'] += len(clean_t)
            df_clean = pd.concat([clean_t, clean_i], ignore_index=True)

    if df_clean is not None:
        dup_mask = df_clean.duplicated(subset=['이름'], keep=False)
        if dup_mask.any():
            df_clean.loc[dup_mask, '이름'] += "(" + df_clean.loc[dup_mask, '지역'] + ")"
            
        st.success(f"✨ 총 **{len(df_clean)}명** 데이터 스캔 완료! (동명이인 분리 완료)")
        
        with st.expander("👉 정리된 전체 명단 확인 (클릭)"):
            df_show = df_clean.drop(columns=['_original_idx']).reset_index(drop=True)
            df_show.index += 1
            st.dataframe(df_show, use_container_width=True)
        
        st.markdown("---")
        
        if st.button("🚀 통합 대진표 생성 실행", use_container_width=True):
            res, t_cnt, m_limit = assign_teams_and_orders(df_clean, h_cnt, p_cnt_indiv, p_cnt_team, max_r)
            
            st.subheader(f"✅ 통합 편성 완료 (총 {t_cnt}조 / 한계 {m_limit}조)")
            
            disp_cols = ['부문', '지역', '이름', '성별', '대진표', '경기', '팀', '구장', '홀', '타순', '_original_idx']
            res_show = res[disp_cols].copy()
            
            res_show = res_show.sort_values(by=['_original_idx']).drop(columns=['_original_idx'])
            res_show.reset_index(drop=True, inplace=True)
            res_show.index += 1
            
            st.dataframe(res_show, use_container_width=True)
            
            st.write("#### 💾 결과물 다운로드")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.download_button("🖨️ 인쇄용 대진표", data=create_print_excel(res, h_cnt), file_name="최종_대진표.xlsx", use_container_width=True)
            with col2:
                # 💡 [핵심] 완벽한 다중조건 동점자 처리 수식이 탑재되었습니다.
                st.download_button("📊 채점표 & 순위표", data=create_scoring_sheet_excel(res), file_name="자동채점_및_순위표.xlsx", use_container_width=True)
            with col3:
                buf = io.BytesIO()
                res_show.to_excel(buf, index=False, sheet_name="검증용_명단")
                st.download_button("📋 원본 검증표", data=buf.getvalue(), file_name="원본순서_검증표.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

except Exception as e:
    st.error(f"🚨 시스템 오류: {e}")
    st.code(traceback.format_exc())