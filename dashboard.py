import asyncio
import io
import re
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from playwright.async_api import async_playwright


st.set_page_config(
    page_title="Google Maps Lead Scraper",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

EXPORT_COLUMNS = [
    "Business Name",
    "Category",
    "Phone",
    "Address",
    "Website",
]

st.markdown(
    """
    <style>
    .main-title {
        font-size: 32px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .subtitle {
        color: #64748b;
        margin-bottom: 25px;
    }
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e2e8f0;
        padding: 15px;
        border-radius: 12px;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
    .stDownloadButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "results" not in st.session_state:
    st.session_state.results = []

if "search_domains" not in st.session_state:
    st.session_state.search_domains = [""]


def clean_text(value):
    if value is None:
        return "N/A"

    value = re.sub(r"\s+", " ", str(value)).strip()
    return value if value else "N/A"


def deduplicate_results(results):
    unique = []
    seen = set()

    for result in results:
        name = clean_text(result.get("Business Name")).lower()
        address = clean_text(result.get("Address")).lower()
        phone = clean_text(result.get("Phone")).lower()

        if address != "n/a":
            key = (name, address)
        else:
            key = (name, phone)

        if key in seen:
            continue

        seen.add(key)
        unique.append(result)

    return unique


async def scrape_google_maps(
    target_query,
    status_placeholder,
    scroll_pause=2500,
    max_idle_scrolls=5,
):
    results = []

    async with async_playwright() as p:
        status_placeholder.info("🌐 Starting Chromium...")

        # IMPORTANT:
        # This is headless=True because the application is running
        # on an Ubuntu server without a graphical desktop.
        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
        )

        encoded_query = quote_plus(target_query)

        maps_url = (
            "https://www.google.com/maps/search/"
            f"{encoded_query}"
        )

        status_placeholder.info(
            f"🔎 Searching Google Maps: **{target_query}**"
        )

        try:
            await page.goto(
                maps_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )
        except Exception as error:
            await browser.close()
            status_placeholder.error(
                f"❌ Could not open Google Maps: {error}"
            )
            return []

        await page.wait_for_timeout(5000)

        feed = page.locator('div[role="feed"]')

        if await feed.count() == 0:
            await browser.close()
            status_placeholder.error(
                "❌ Google Maps results panel could not be found."
            )
            return []

        previous_count = 0
        idle_scrolls = 0
        scroll_number = 0

        while True:
            scroll_number += 1

            cards = page.locator('div[role="article"]')
            current_count = await cards.count()

            status_placeholder.info(
                f"📜 Loading results... "
                f"Scroll #{scroll_number} — "
                f"**{current_count} listings found**"
            )

            await feed.evaluate(
                """
                element => {
                    element.scrollTo(
                        0,
                        element.scrollHeight
                    );
                }
                """
            )

            await page.wait_for_timeout(scroll_pause)

            cards = page.locator('div[role="article"]')
            new_count = await cards.count()

            if new_count > previous_count:
                idle_scrolls = 0
                status_placeholder.info(
                    f"📜 Scroll #{scroll_number} — "
                    f"**{new_count} listings loaded**"
                )
            else:
                idle_scrolls += 1
                status_placeholder.warning(
                    f"⏳ No new listings loaded "
                    f"({idle_scrolls}/{max_idle_scrolls})"
                )

            previous_count = new_count

            if idle_scrolls >= max_idle_scrolls:
                status_placeholder.success(
                    "✅ Google Maps appears to have stopped "
                    f"loading new results. Total: **{new_count}**"
                )
                break

            end_text = page.locator(
                "text=You've reached the end of the list"
            )

            if await end_text.count() > 0:
                status_placeholder.success(
                    "✅ Reached the end of the Google Maps "
                    f"results list. Total: **{new_count}**"
                )
                break

        places = page.locator('div[role="article"]')
        total = await places.count()

        status_placeholder.info(
            f"📋 Extracting details from **{total} listings**..."
        )

        for index in range(total):
            try:
                place = places.nth(index)

                name_element = place.locator(
                    'div.fontHeadlineSmall'
                )

                if await name_element.count() == 0:
                    continue

                name = await name_element.first.text_content()
                name = clean_text(name)

                if name == "N/A":
                    continue

                await place.click(timeout=10000)
                await page.wait_for_timeout(1800)

                address_element = page.locator(
                    'button[data-item-id="address"]'
                )

                if await address_element.count() > 0:
                    address = await (
                        address_element.first.text_content()
                    )
                else:
                    address = "N/A"

                phone_element = page.locator(
                    'button[data-item-id^="phone:tel:"]'
                )

                if await phone_element.count() > 0:
                    phone = await phone_element.first.text_content()
                else:
                    phone = "N/A"

                website_element = page.locator(
                    'a[data-item-id="authority"]'
                )

                if await website_element.count() > 0:
                    website = await (
                        website_element.first.get_attribute("href")
                    )
                else:
                    website = "N/A"

                results.append(
                    {
                        "Business Name": name,
                        "Category": target_query,
                        "Phone": clean_text(phone),
                        "Address": clean_text(address),
                        "Website": clean_text(website),
                    }
                )

                status_placeholder.success(
                    f"✅ {index + 1}/{total} — {name}"
                )

            except Exception as error:
                status_placeholder.warning(
                    f"⚠️ Skipped listing {index + 1}/{total}: "
                    f"{str(error)[:100]}"
                )

        await browser.close()

    return results


def create_excel(df):
    output = io.BytesIO()

    export_df = df[
        [column for column in EXPORT_COLUMNS if column in df.columns]
    ].copy()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(
            writer,
            index=False,
            sheet_name="Leads",
        )

        worksheet = writer.sheets["Leads"]
        worksheet.freeze_panes = "A2"

        from openpyxl.styles import Font

        for cell in worksheet[1]:
            cell.font = Font(bold=True)

        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter

            for cell in column:
                if cell.value:
                    max_length = max(
                        max_length,
                        len(str(cell.value))
                    )

            worksheet.column_dimensions[column_letter].width = min(
                max_length + 3,
                60,
            )

    output.seek(0)
    return output.getvalue()


def create_csv(df):
    export_df = df[
        [column for column in EXPORT_COLUMNS if column in df.columns]
    ].copy()

    return (
        export_df
        .to_csv(index=False, encoding="utf-8-sig")
        .encode("utf-8-sig")
    )


with st.sidebar:
    st.title("📊 Lead Scraper")
    st.caption("Google Maps Business Lead Generator")

    st.divider()

    st.subheader("⚙️ Scraper Settings")

    scroll_pause = st.slider(
        "Scroll Wait Time",
        min_value=1000,
        max_value=5000,
        value=2500,
        step=500,
        help="Time to wait after each scroll.",
    )

    max_idle_scrolls = st.slider(
        "Stop After No New Results",
        min_value=2,
        max_value=15,
        value=5,
        help=(
            "Stop after this many consecutive scrolls "
            "produce no new listings."
        ),
    )

    st.divider()

    st.info(
        "No database is used. Results exist only during "
        "the current Streamlit session and can be downloaded."
    )


st.markdown(
    '<div class="main-title">📊 Google Maps Lead Scraper</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Find businesses by category and city, view the results "
    "and download them."
    "</div>",
    unsafe_allow_html=True,
)

st.subheader("🏢 Business Domains / Categories")

st.caption(
    "Enter one domain or add multiple domains."
)

domains_to_remove = []

for index in range(len(st.session_state.search_domains)):
    col1, col2 = st.columns([10, 1])

    with col1:
        value = st.text_input(
            f"Domain {index + 1}",
            value=st.session_state.search_domains[index],
            key=f"domain_{index}",
            placeholder="Example: CSC Center",
        )

        st.session_state.search_domains[index] = value

    with col2:
        st.write("")

        if len(st.session_state.search_domains) > 1:
            if st.button(
                "🗑️",
                key=f"remove_domain_{index}",
                help="Remove this domain",
            ):
                domains_to_remove.append(index)

if domains_to_remove:
    for index in reversed(domains_to_remove):
        del st.session_state.search_domains[index]

    st.rerun()

if st.button("➕ Add another domain"):
    st.session_state.search_domains.append("")
    st.rerun()

st.divider()

st.subheader("📍 Search Location")

city = st.text_input(
    "City / Location",
    placeholder="Example: Lucknow",
)

st.divider()

domains = [
    domain.strip()
    for domain in st.session_state.search_domains
    if domain.strip()
]

if city.strip() and domains:
    st.subheader("🔎 Search Preview")

    for domain in domains:
        st.code(
            f"{domain} in {city.strip()}",
            language=None,
        )

st.divider()

start = st.button(
    "🚀 Start Scraping",
    type="primary",
    use_container_width=True,
)

if start:
    domains = [
        domain.strip()
        for domain in st.session_state.search_domains
        if domain.strip()
    ]

    if not domains:
        st.error("❌ Please enter at least one business domain.")
        st.stop()

    if not city.strip():
        st.error("❌ Please enter a city or location.")
        st.stop()

    unique_domains = []
    seen_domains = set()

    for domain in domains:
        normalized = domain.lower()

        if normalized not in seen_domains:
            seen_domains.add(normalized)
            unique_domains.append(domain)

    domains = unique_domains

    st.session_state.results = []

    st.subheader("🔎 Search Plan")
    st.write(f"**Location:** {city.strip()}")
    st.write(f"**Domains:** {len(domains)}")

    for domain in domains:
        st.write(f"• {domain} in {city.strip()}")

    st.divider()

    progress = st.progress(0)
    status_placeholder = st.empty()

    total_found = 0

    for domain_index, domain in enumerate(domains):
        search_query = f"{domain} in {city.strip()}"

        status_placeholder.info(
            f"🔎 Searching: **{search_query}**"
        )

        try:
            results = asyncio.run(
                scrape_google_maps(
                    target_query=search_query,
                    status_placeholder=status_placeholder,
                    scroll_pause=scroll_pause,
                    max_idle_scrolls=max_idle_scrolls,
                )
            )

            categorized_results = []

            for result in results:
                categorized_results.append(
                    {
                        "Business Name": result.get(
                            "Business Name",
                            "N/A",
                        ),
                        "Category": domain,
                        "Phone": result.get(
                            "Phone",
                            "N/A",
                        ),
                        "Address": result.get(
                            "Address",
                            "N/A",
                        ),
                        "Website": result.get(
                            "Website",
                            "N/A",
                        ),
                    }
                )

            st.session_state.results.extend(
                categorized_results
            )

            total_found += len(categorized_results)

            st.success(
                f"✅ **{domain}** completed — "
                f"{len(categorized_results)} businesses collected."
            )

        except Exception as error:
            st.error(
                f"❌ Error while scraping **{domain}**: {error}"
            )

        progress.progress(
            (domain_index + 1) / len(domains)
        )

    st.session_state.results = deduplicate_results(
        st.session_state.results
    )

    final_count = len(st.session_state.results)
    duplicates_removed = total_found - final_count

    st.divider()
    st.subheader("🎉 Scraping Completed")

    col1, col2, col3 = st.columns(3)

    col1.metric("Businesses Found", total_found)
    col2.metric("Unique Businesses", final_count)
    col3.metric("Duplicates Removed", duplicates_removed)

    st.success(
        f"Completed {len(domains)} domain(s) in {city.strip()}."
    )


st.divider()
st.subheader("📋 Scraped Business Data")

if not st.session_state.results:
    st.info(
        "No data available yet. Enter your domains and city, "
        "then click Start Scraping."
    )
else:
    results_df = pd.DataFrame(st.session_state.results)

    results_df = results_df[
        [
            column
            for column in EXPORT_COLUMNS
            if column in results_df.columns
        ]
    ]

    search = st.text_input(
        "🔎 Filter Results",
        placeholder=(
            "Search business name, category, phone, "
            "address or website..."
        ),
    )

    filtered_df = results_df.copy()

    if search.strip():
        mask = (
            filtered_df.astype(str)
            .apply(
                lambda column: column.str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                )
            )
            .any(axis=1)
        )

        filtered_df = filtered_df[mask]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Businesses", len(results_df))
    col2.metric("Displayed", len(filtered_df))

    col3.metric(
        "With Phone",
        len(results_df[results_df["Phone"] != "N/A"]),
    )

    col4.metric(
        "With Website",
        len(results_df[results_df["Website"] != "N/A"]),
    )

    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=600,
        hide_index=True,
        column_config={
            "Business Name": st.column_config.TextColumn(
                "Business Name",
                width="medium",
            ),
            "Category": st.column_config.TextColumn(
                "Category",
                width="medium",
            ),
            "Phone": st.column_config.TextColumn(
                "Phone",
                width="medium",
            ),
            "Address": st.column_config.TextColumn(
                "Address",
                width="large",
            ),
            "Website": st.column_config.LinkColumn(
                "Website",
                width="medium",
            ),
        },
    )

    st.divider()
    st.subheader("📥 Download Results")

    st.caption(
        "Exports contain only Business Name, Category, Phone, "
        "Address and Website."
    )

    download_col1, download_col2 = st.columns(2)

    with download_col1:
        st.download_button(
            "📄 Download CSV",
            data=create_csv(results_df),
            file_name="google_maps_business_leads.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with download_col2:
        st.download_button(
            "📊 Download Excel",
            data=create_excel(results_df),
            file_name="google_maps_business_leads.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    st.divider()

    if st.button(
        "🗑️ Clear Current Results",
        use_container_width=True,
    ):
        st.session_state.results = []
        st.success("Current results cleared.")
        st.rerun()
