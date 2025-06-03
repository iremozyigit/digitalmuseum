import streamlit as st
import pandas as pd
import random
import time
import os
import io
import requests
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from textwrap import wrap
from PIL import Image as PILImage
import gspread
from google.oauth2.service_account import Credentials
import json
import hashlib

# --- Set up connection to Google Sheets ---
@st.cache_resource
def init_google_sheets():
    """Initialize Google Sheets connection with caching"""
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials_dict = st.secrets["gspread"]
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"❌ Failed to initialize Google Sheets: {e}")
        return None

# Initialize client
client = init_google_sheets()

# --- Test Google Sheets Connection ---
if client:
    try:
        test_sheet = client.open("Digital Museum Streamlit Data Sheet").sheet1
        
    except Exception as e:
        st.error(f"❌ Failed to connect to Google Sheets: {e}")
        client = None

# --- Write to Google Sheets Function ---
def write_dataframe_to_sheets(sheet, df: pd.DataFrame):
    """Write DataFrame to Google Sheets with error handling"""
    try:
        if df.empty:
            st.warning("DataFrame is empty, skipping write operation.")
            return False
        
        
        
        # Convert DataFrame to list of lists, handling NaN values
        rows = df.fillna('').astype(str).values.tolist()
        
        # Check if sheet is empty using a more robust method
        try:
            # Try to get all values first
            all_values = sheet.get_all_values()
            sheet_is_empty = len(all_values) == 0 or (len(all_values) == 1 and all(cell == '' for cell in all_values[0]))
            st.info(f"Sheet has {len(all_values)} rows, is_empty: {sheet_is_empty}")
        except Exception as e:
            # If get_all_values fails, assume sheet is empty
            st.warning(f"Could not check sheet contents, assuming empty: {e}")
            sheet_is_empty = True
        
        # Add headers if sheet is empty
        if sheet_is_empty:
            headers = df.columns.tolist()
            st.info(f"Adding headers: {headers}")
            sheet.append_row(headers, value_input_option="USER_ENTERED")
        
        # Append data rows
        st.info(f"Appending {len(rows)} data rows...")
        for i, row in enumerate(rows):
            try:
                sheet.append_row(row, value_input_option="USER_ENTERED")
            except Exception as e:
                st.error(f"Failed to append row {i+1}: {e}")
                st.error(f"Row data: {row}")
                raise
        
        st.success("✅ Success.")
        return True
        
    except Exception as e:
        st.error(f"❌ Failed to write DataFrame to Google Sheets: {e}")
        st.error(f"DataFrame shape: {df.shape}")
        st.error(f"DataFrame columns: {list(df.columns)}")
        return False
# --- Load Data ---
@st.cache_data
def load_museum_data():
    """Load museum data with caching"""
    base_path = os.path.dirname(__file__)
    file_path = os.path.join(base_path, 'data', 'real_museum_metadata_with_ai.json')
    
    if os.path.exists(file_path):
        return pd.read_json(file_path)
    else:
        st.error(f"Metadata file not found at {file_path}. Please check your data folder.")
        st.stop()

data = load_museum_data()

# --- Data Writing Function ---
def write_data_to_sheets():
    """Write data to Google Sheets"""
    if not client:
        st.error("Google Sheets client not available")
        return
    
    try:
        # Create df_views from session state
        df_views = pd.DataFrame(st.session_state.viewed_items)
        if not df_views.empty:
            df_views["user_code"] = st.session_state.user_code
            df_views["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

        # Create df_summary if curation exists
        if "curated_exhibition" in st.session_state:
            exhibition = st.session_state.curated_exhibition
            df_summary = pd.DataFrame([{
                "exhibition_title": exhibition.get("exhibition_title", ""),
                "exhibition_description": exhibition.get("exhibition_description", ""),
                "selected_ids": ", ".join(exhibition.get("selected_ids", [])),
                "preferences": json.dumps(exhibition.get("preferences", {}), ensure_ascii=False),
                "user_code": st.session_state.user_code,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }])
        else:
            df_summary = pd.DataFrame()

        # Write to sheets
        views_sheet = client.open("Digital Museum Streamlit Data Sheet").worksheet("Artwork Views")
        summary_sheet = client.open("Digital Museum Streamlit Data Sheet").worksheet("Exhibition Summary")

        success = True
        if not df_views.empty:
            success &= write_dataframe_to_sheets(views_sheet, df_views)
        if not df_summary.empty:
            success &= write_dataframe_to_sheets(summary_sheet, df_summary)

        if success:
            st.session_state.written_to_sheets = True

    except Exception as e:
        st.error(f"❌ Failed to write data to Google Sheets: {e}")

# --- Setup Session State ---
def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        "start_times": {},
        "viewed_items": [],
        "index": 0,
        "selected_indices": random.sample(range(len(data)), min(20, len(data))),
        "exhibition_title": "",
        "exhibition_description": "",
        "preferences": {},
        "exhibition_stage": "select_artworks",
        "written_to_sheets": False,
        "user_code": "",
        "group": None
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()

st.markdown("""
    ### 🎨 Welcome to the Digital Museum Experience

    You'll view 20 artworks, each with a short description.  
    At the end, you are invited to curate your own mini-exhibition (optional) and then complete a short final questionnaire.

    👉 **Note**: We recommend completing this in one sitting, in a quiet place where you can stay focused. Please don’t refresh or go back, as your progress may be lost.
    """)

# --- Ask for User Code to Identify Later ---
prev_code = st.session_state.user_code
st.session_state.user_code = st.text_input("Enter your 4-letter participant code:", value=prev_code)

if st.session_state.user_code and len(st.session_state.user_code) != 4:
    st.warning("Please enter a 4-letter participant code.")


# --- Assign group deterministically ---
if st.session_state.user_code and not st.session_state.group:
    hash_digest = hashlib.sha256(st.session_state.user_code.encode()).hexdigest()
    group_value = int(hash_digest, 16) % 2
    st.session_state.group = "ai" if group_value == 0 else "curator"

# --- PDF Generation Function ---
def generate_exhibition_pdf(title, description, artwork_ids, data, preferences):
    """Generate PDF exhibition card"""
    import tempfile
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    margin = 1 * inch
    text_width = width - 2 * margin
    image_width = width - 2 * margin
    image_height = 4 * inch

    # Cover Page
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.HexColor("#2c3e50"))
    c.drawCentredString(width / 2, height - 2 * inch, title)

    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#333333"))
    wrapped_intro = wrap(description, width=80)
    text = c.beginText(margin, height - 2.5 * inch)
    text.setLeading(18)
    for line in wrapped_intro:
        text.textLine(line)
    c.drawText(text)
    c.showPage()

    for aid in artwork_ids:
        try:
            row = data[data['id'] == aid].iloc[0]
            artwork_title = row['title']
            theme = row.get('theme', 'Unknown')
            img_url = row['image_url']

            pref = preferences.get(aid)
            if not pref:
                continue

            chosen = pref['user_choice']
            chosen_desc = row['description'] if pref['description_A_source'] == 'curator' and chosen == 'Description A' else \
                           row['ai_story'] if pref['description_A_source'] == 'ai' and chosen == 'Description A' else \
                           row['description'] if pref['description_B_source'] == 'curator' else row['ai_story']

            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, width, height, stroke=0, fill=1)

            c.setFont("Helvetica-Bold", 18)
            c.setFillColor(colors.HexColor("#2c3e50"))
            c.drawCentredString(width / 2, height - 1 * inch, artwork_title)

            c.setFont("Helvetica", 12)
            c.setFillColor(colors.HexColor("#7f8c8d"))
            c.drawCentredString(width / 2, height - 1.3 * inch, f"Theme: {theme}")

            y = height - 2 * inch

            try:
                response = requests.get(img_url, stream=True, timeout=10)
                if response.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                        tmp_file.write(response.content)
                        tmp_file_path = tmp_file.name
                    c.drawImage(tmp_file_path, margin, y - image_height, width=image_width, height=image_height, preserveAspectRatio=True, anchor='n', mask='auto')
                    os.unlink(tmp_file_path)
                    y -= image_height + 0.3 * inch
                else:
                    raise Exception("Image fetch failed")
            except:
                c.setFont("Helvetica", 10)
                c.setFillColor(colors.red)
                c.drawCentredString(width / 2, y, "[Image could not be loaded]")
                y -= 0.4 * inch

            c.setFont("Helvetica", 11)
            c.setFillColor(colors.black)
            wrapped_desc = []
            for paragraph in chosen_desc.split("\n"):
                wrapped_desc.extend(wrap(paragraph, width=100))

            text = c.beginText(margin, y)
            text.setLeading(14)
            for line in wrapped_desc:
                text.textLine(line)
            c.drawText(text)

            c.showPage()
        except Exception as e:
            st.error(f"Error processing artwork {aid}: {e}")
            continue

    c.save()
    buffer.seek(0)
    return buffer

# --- Main App Logic ---
if st.session_state.user_code and len(st.session_state.user_code) == 4:
    
    
    if st.session_state.index < len(st.session_state.selected_indices):
        artwork = data.iloc[st.session_state.selected_indices[st.session_state.index]]

        st.image(artwork['image_url'], use_container_width=True)
        st.subheader(artwork['title'])
        st.caption(f"Artist: {artwork.get('artist', 'Unknown')}")

        description_text = artwork['description'] if st.session_state.group == "curator" else artwork.get('ai_story', None)
        st.write(description_text if description_text else "No description available for this artwork.")

        if artwork['id'] not in st.session_state.start_times:
            st.session_state.start_times[artwork['id']] = time.time()

        if st.button("Next", key=f"next_{artwork['id']}"):
            end_time = time.time()
            time_spent = end_time - st.session_state.start_times[artwork['id']]

            st.session_state.viewed_items.append({
                "artwork_id": artwork['id'],
                "title": artwork['title'],
                "time_spent_seconds": round(time_spent, 2),
                "group": st.session_state.group
            })

            st.session_state.index += 1
            st.rerun()

    else:
        st.markdown("---")
        st.subheader("Curator Mode: Build Your Own Exhibition")

        proceed = st.radio(
            "Choose an option:",
            ["Yes, I want to build an exhibition", "No, I want to skip this step"],
            key="curator_choice"
        )

        if proceed == "Yes, I want to build an exhibition":
            viewed_df = pd.DataFrame(st.session_state.viewed_items)
            selected_titles = []

            if st.session_state.exhibition_stage == "select_artworks":
                st.markdown("#### Select artworks to include in your exhibition:")
                col_left, col_right = st.columns(2)
                for i, row in enumerate(viewed_df.itertuples()):
                    col = col_left if i % 2 == 0 else col_right
                    with col:
                        st.markdown("**Select**")
                        if st.checkbox("select", key=f"select_{row.artwork_id}_{i}", label_visibility="collapsed"):
                            selected_titles.append(row.artwork_id)
                        st.image(data[data['id'] == row.artwork_id].iloc[0]['image_url'], width=160)
                        st.caption(row.title)

                if st.button("Save My Exhibition and Pick Descriptions for Artworks", key="save_exhibition"):
                    if not selected_titles:
                        st.error("Please select at least 1 artwork to proceed.")
                    else:
                        st.session_state.exhibition_stage = "pick_descriptions"
                        st.session_state.selected_titles = selected_titles
                        st.rerun()

            elif st.session_state.exhibition_stage == "pick_descriptions":
                selected_titles = st.session_state.selected_titles
                st.success("Artworks selected. Now select which description you'd include for each artwork.")
                for artwork_id in selected_titles:
                    artwork_row = data[data['id'] == artwork_id].iloc[0]
                    title = artwork_row['title']
                    image_url = artwork_row['image_url']
                    curator_desc = artwork_row['description'] or "No curator description available."
                    ai_desc = artwork_row['ai_story'] or "No AI-generated description available."

                    desc_key = f"description_order_{artwork_id}"
                    if desc_key not in st.session_state:
                        descriptions = [("A", curator_desc, "curator"), ("B", ai_desc, "ai")]
                        random.shuffle(descriptions)
                        st.session_state[desc_key] = descriptions
                    else:
                        descriptions = st.session_state[desc_key]

                    st.markdown(f"### {title}")
                    st.image(image_url, width=400)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Description A**")
                        st.write(descriptions[0][1])
                    with col2:
                        st.markdown("**Description B**")
                        st.write(descriptions[1][1])

                    choice = st.radio(
                        f"Which description would you include for '{title}'?",
                        ["Description A", "Description B"],
                        key=f"preference_{artwork_id}"
                    )

                    st.session_state.preferences[artwork_id] = {
                        "artwork_title": title,
                        "user_choice": choice,
                        "description_A_source": descriptions[0][2],
                        "description_B_source": descriptions[1][2]
                    }

                st.markdown("---")
                st.subheader("Finalize Your Exhibition")

                st.session_state.exhibition_title = st.text_input("Give your exhibition a title:", value=st.session_state.exhibition_title, key="exhibition_title_input")
                st.session_state.exhibition_description = st.text_area("Describe your theme in 1–2 sentences:", value=st.session_state.exhibition_description, key="exhibition_description_input")

                if st.button("Save My Exhibition", key="finalize_exhibition"):
                    if not st.session_state.exhibition_title or not st.session_state.exhibition_description:
                        st.error("Please provide a title and description to save your exhibition.")
                    else:
                        st.session_state.curated_exhibition = {
                            "selected_ids": selected_titles,
                            "exhibition_title": st.session_state.exhibition_title,
                            "exhibition_description": st.session_state.exhibition_description,
                            "preferences": st.session_state.preferences
                        }
                        st.success("Your exhibition has been saved!")

                        # Write data to Google Sheets immediately
                        if client and not st.session_state.written_to_sheets:
                            write_data_to_sheets()

                        st.markdown("---")
                        st.title("Thank you for participating!")
                        st.write("You have completed the session.")
                        st.write("Please continue to the final survey here:")
                        st.markdown("[Go to Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMmbXk8-9qoEygXBqcBY2gAqiGrzDms48tcf0j_ax-px56pg/viewform?usp=header)")

        else:
            st.info("You chose to skip Curator Mode.")
            
            # Write data to Google Sheets even if skipping
            if client and not st.session_state.written_to_sheets:
                write_data_to_sheets()

            st.markdown("---")
            st.title("Thank you for participating!")
            st.write("You have completed the session.")
            st.write("Please continue to the final survey here:")
            st.markdown("[Go to Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMmbXk8-9qoEygXBqcBY2gAqiGrzDms48tcf0j_ax-px56pg/viewform?usp=header)")

# --- Downloads if Exhibition Was Created ---
if "curated_exhibition" in st.session_state:
    exhibition = st.session_state.curated_exhibition

    st.markdown("---")
    st.subheader("Download Your Exhibition Card (PDF)")
    
    try:
        pdf_buffer = generate_exhibition_pdf(
            title=exhibition['exhibition_title'],
            description=exhibition['exhibition_description'],
            artwork_ids=exhibition['selected_ids'],
            data=data,
            preferences=exhibition['preferences']
        )

        st.download_button(
            label="Download Exhibition Card (PDF)",
            data=pdf_buffer,
            file_name="my_exhibition_card.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"Error generating PDF: {e}")

    # CSV downloads
    df_views = pd.DataFrame(st.session_state.viewed_items)
    if not df_views.empty:
        df_views["user_code"] = st.session_state.user_code
        df_views["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        st.download_button(
            label="Download Artwork Views (CSV)",
            data=df_views.to_csv(index=False).encode('utf-8'),
            file_name="artwork_views.csv",
            mime="text/csv"
        )

    df_summary = pd.DataFrame([{
        "exhibition_title": exhibition.get("exhibition_title", ""),
        "exhibition_description": exhibition.get("exhibition_description", ""),
        "selected_ids": ", ".join(exhibition.get("selected_ids", [])),
        "preferences": json.dumps(exhibition.get("preferences", {}), indent=2)
    }])

    st.download_button(
        label="Download Exhibition Summary (CSV)",
        data=df_summary.to_csv(index=False).encode('utf-8'),
        file_name="exhibition_summary.csv",
        mime="text/csv"
    )

# --- Show user code prompt if not provided ---
if not st.session_state.user_code or len(st.session_state.user_code) != 4:
    st.write("Please enter your 4-letter participant code to continue.")
