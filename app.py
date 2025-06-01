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


    
# --- Set up connection to Google Sheets ---
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials_dict = st.secrets["gspread"]
credentials = Credentials.from_service_account_info(credentials_dict, scopes=scope)
client = gspread.authorize(credentials)

# --- Test Google Sheets Connection ---
try:
    test_sheet = client.open("Digital Museum Streamlit Data Sheet").sheet1  # Replace with actual sheet name
    st.success("✅ Successfully connected to Google Sheets and wrote a test row.")
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

# --- Main App Logic ---
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
    st.title("Thank you for participating!")
    st.write("You have completed the main session.")
    st.write("Please continue to the final survey here:")
    st.markdown("[Go to Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMmbXk8-9qoEygXBqcBY2gAqiGrzDms48tcf0j_ax-px56pg/viewform?usp=header)")

    st.markdown("---")
    st.subheader("Curator Mode: Build Your Own Exhibition")

    st.write("Would you like to create your own mini-exhibition from the artworks you just saw? (Optional)")
    proceed = st.radio("Choose an option:", ["Yes, I want to build an exhibition", "No, I want to skip this step"], key="curator_choice")

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
                    if st.checkbox("", key=f"select_{row.artwork_id}_{i}"):
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

    else:
        st.info("You chose to skip Curator Mode. Thank you for participating!")

    # --- PDF Generation Function ---
    def generate_exhibition_pdf(title, description, artwork_ids, data, preferences):
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
                response = requests.get(img_url, stream=True)
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

        c.save()
        buffer.seek(0)
        return buffer

    if "curated_exhibition" in st.session_state:
        st.markdown("---")
        st.subheader("Download Your Exhibition Card (PDF)")

        exhibition = st.session_state.curated_exhibition
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

        df_views = pd.DataFrame(st.session_state.viewed_items)
        df_summary = pd.DataFrame([{
            "exhibition_title": exhibition.get("exhibition_title", ""),
            "exhibition_description": exhibition.get("exhibition_description", ""),
            "selected_ids": ", ".join(exhibition.get("selected_ids", [])),
            "preferences": json.dumps(exhibition.get("preferences", {}), indent=2)
        }])

        st.download_button(
            label="Download Artwork Views (CSV)",
            data=df_views.to_csv(index=False).encode('utf-8'),
            file_name="artwork_views.csv",
            mime="text/csv"
        )

        st.download_button(
            label="Download Exhibition Summary (CSV)",
            data=df_summary.to_csv(index=False).encode('utf-8'),
            file_name="exhibition_summary.csv",
            mime="text/csv"
        )
