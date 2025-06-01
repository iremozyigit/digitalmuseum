import streamlit as st
import pandas as pd
import random
import time
import os
import io
import requests
import uuid
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

# --- Set up connection to Google Sheets ---
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials_dict = st.secrets["gspread"]
credentials = Credentials.from_service_account_info(credentials_dict, scopes=scope)
client = gspread.authorize(credentials)

# --- Test Google Sheets Connection ---
try:
    test_sheet = client.open("Digital Museum Streamlit Data Sheet").sheet1
except Exception as e:
    st.error(f"❌ Failed to connect to Google Sheets: {e}")

# --- Load Data ---
base_path = os.path.dirname(__file__)
file_path = os.path.join(base_path, 'data', 'real_museum_metadata_with_ai.json')

if os.path.exists(file_path):
    data = pd.read_json(file_path)
else:
    st.error(f"Metadata file not found at {file_path}. Please check your data folder.")
    st.stop()

# --- Setup Session State ---
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())
if "group" not in st.session_state:
    st.session_state.group = random.choice(["curator", "ai"])
if "start_times" not in st.session_state:
    st.session_state.start_times = {}
if "viewed_items" not in st.session_state:
    st.session_state.viewed_items = []
if "index" not in st.session_state:
    st.session_state.index = 0
if "selected_indices" not in st.session_state:
    st.session_state.selected_indices = random.sample(range(len(data)), 20)
if "exhibition_title" not in st.session_state:
    st.session_state.exhibition_title = ""
if "exhibition_description" not in st.session_state:
    st.session_state.exhibition_description = ""
if "preferences" not in st.session_state:
    st.session_state.preferences = {}
if "exhibition_stage" not in st.session_state:
    st.session_state.exhibition_stage = "select_artworks"
if "data_saved" not in st.session_state:
    st.session_state.data_saved = False

# --- Main App Logic ---
if st.session_state.index < len(st.session_state.selected_indices):
    artwork = data.iloc[st.session_state.selected_indices[st.session_state.index]]

    st.image(artwork['image_url'])
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
            "user_id": st.session_state.user_id,
            "artwork_id": artwork['id'],
            "title": artwork['title'],
            "time_spent_seconds": round(time_spent, 2),
            "group": st.session_state.group
        })

        st.session_state.index += 1
        st.rerun()

else:
    st.title("Thank you for participating!")
    st.write("You have completed the main session.")
    st.write("Please continue to the final survey here:")

    if not st.session_state.data_saved:
        try:
            sheet = client.open("Digital Museum Streamlit Data Sheet").sheet1
            df_views = pd.DataFrame(st.session_state.viewed_items)
            if not df_views.empty:
                sheet.append_rows([df_views.columns.tolist()] + df_views.values.tolist())
            
            if "curated_exhibition" in st.session_state:
                curated = st.session_state.curated_exhibition
                curator_data = {
                    "user_id": st.session_state.user_id,
                    "exhibition_title": curated["exhibition_title"],
                    "exhibition_description": curated["exhibition_description"],
                    "selected_artworks": ", ".join(curated["selected_ids"]),
                    "preferences": json.dumps(curated["preferences"])
                }
                curator_df = pd.DataFrame([curator_data])
                curator_sheet = client.open("Digital Museum Streamlit Data Sheet").worksheet("Curator Mode")
                curator_sheet.append_rows([curator_df.columns.tolist()] + curator_df.values.tolist())

            st.session_state.data_saved = True
            st.success("✅ Your interaction data has been saved to Google Sheets.")
        except Exception as e:
            st.error(f"❌ Failed to save data to Google Sheets: {e}")

    st.markdown("[Go to Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMmbXk8-9qoEygXBqcBY2gAqiGrzDms48tcf0j_ax-px56pg/viewform?usp=header)")

# --- Place the following at the end of your Streamlit script ---

if st.session_state.index >= len(st.session_state.selected_indices):
    st.title("Thank you for participating!")
    st.write("You have completed the main session.")

    if not st.session_state.get("data_saved", False):
        try:
            sheet = client.open("Digital Museum Streamlit Data Sheet").worksheet("Viewer Data")
            df_views = pd.DataFrame(st.session_state.viewed_items)
            df_views.insert(0, "user_id", st.session_state.user_id)
            if not df_views.empty:
                sheet.append_rows([df_views.columns.tolist()] + df_views.values.tolist())
            st.session_state.data_saved = True
        except Exception as e:
            st.error(f"❌ Failed to save viewer data to Google Sheets: {e}")


    st.subheader("Curator Mode: Build Your Own Exhibition")

    proceed = st.radio("Would you like to create a mini-exhibition from the artworks you just saw?", ["Yes", "No"], key="curator_choice")

    if proceed == "Yes":
        if "curator_stage" not in st.session_state:
            st.session_state.curator_stage = "select_artworks"
        selected_titles = []

        if st.session_state.curator_stage == "select_artworks":
            st.markdown("### Select artworks for your exhibition")
            viewed_df = pd.DataFrame(st.session_state.viewed_items)
            col_left, col_right = st.columns(2)
            for i, row in enumerate(viewed_df.itertuples()):
                col = col_left if i % 2 == 0 else col_right
                with col:
                    if st.checkbox("", key=f"select_{row.artwork_id}"):
                        selected_titles.append(row.artwork_id)
                    st.image(data[data['id'] == row.artwork_id].iloc[0]['image_url'], width=150)
                    st.caption(row.title)

            if st.button("Next: Choose Descriptions"):
                if not selected_titles:
                    st.warning("Please select at least one artwork.")
                else:
                    st.session_state.selected_titles = selected_titles
                    st.session_state.curator_stage = "pick_descriptions"
                    st.rerun()

        elif st.session_state.curator_stage == "pick_descriptions":
            preferences = {}
            for aid in st.session_state.selected_titles:
                row = data[data['id'] == aid].iloc[0]
                st.markdown(f"### {row['title']}")
                curator_desc = row['description'] or "No curator description."
                ai_desc = row['ai_story'] or "No AI-generated description."
                options = [("A", curator_desc, "curator"), ("B", ai_desc, "ai")]
                random.shuffle(options)
                st.radio(f"Choose a description:", ["A", "B"], key=f"desc_{aid}")
                preferences[aid] = {
                    "title": row['title'],
                    "A": options[0][1],
                    "B": options[1][1],
                    "A_source": options[0][2],
                    "B_source": options[1][2]
                }

            st.session_state.curator_preferences = preferences
            st.session_state.curator_stage = "finalize"
            st.rerun()

        elif st.session_state.curator_stage == "finalize":
            title = st.text_input("Exhibition Title")
            desc = st.text_area("Describe your exhibition")

            if st.button("Save and Download PDF"):
                # Save to Google Sheets
                try:
                    sheet = client.open("Digital Museum Streamlit Data Sheet").worksheet("Curator Mode")
                    summary = pd.DataFrame([{
                        "user_id": st.session_state.user_id,
                        "exhibition_title": title,
                        "exhibition_description": desc,
                        "selected_ids": ", ".join(st.session_state.selected_titles),
                        "preferences": json.dumps(st.session_state.curator_preferences)
                    }])
                    sheet.append_rows([summary.columns.tolist()] + summary.values.tolist())
                    st.success("✅ Curator mode data saved.")
                except Exception as e:
                    st.error(f"❌ Failed to save curator data: {e}")

                # Generate and download PDF
                def generate_exhibition_pdf(title, description, artwork_ids, data, preferences):
                    buffer = io.BytesIO()
                    c = canvas.Canvas(buffer, pagesize=letter)
                    width, height = letter
                    margin = 1 * inch
                    image_height = 4 * inch
                    c.setFont("Helvetica-Bold", 24)
                    c.drawCentredString(width / 2, height - 1.5 * inch, title)
                    c.setFont("Helvetica", 12)
                    wrapped = wrap(description, 100)
                    text = c.beginText(margin, height - 2.5 * inch)
                    for line in wrapped:
                        text.textLine(line)
                    c.drawText(text)
                    c.showPage()

                    for aid in artwork_ids:
                        row = data[data['id'] == aid].iloc[0]
                        img_url = row['image_url']
                        try:
                            response = requests.get(img_url)
                            img = PILImage.open(io.BytesIO(response.content))
                            temp_path = f"temp_{aid}.png"
                            img.save(temp_path)
                            c.drawImage(temp_path, margin, height - image_height - inch, width=width - 2*margin, height=image_height)
                            os.remove(temp_path)
                        except:
                            c.drawString(margin, height - image_height - inch, "[Image unavailable]")

                        c.drawString(margin, height - image_height - inch - 20, f"{row['title']}")
                        chosen = st.session_state.curator_preferences[aid]
                        chosen_text = chosen[st.session_state[f"desc_{aid}"].lower()]
                        wrapped = wrap(chosen_text, 100)
                        text = c.beginText(margin, height - image_height - inch - 40)
                        for line in wrapped:
                            text.textLine(line)
                        c.drawText(text)
                        c.showPage()

                    c.save()
                    buffer.seek(0)
                    return buffer

                pdf = generate_exhibition_pdf(title, desc, st.session_state.selected_titles, data, st.session_state.curator_preferences)
                st.download_button("Download Exhibition Card", data=pdf, file_name="exhibition.pdf", mime="application/pdf")

    st.markdown("[Go to Survey](https://docs.google.com/forms/...)\n---")

