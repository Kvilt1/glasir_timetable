import logging
import re
from typing import Dict

from bs4 import BeautifulSoup, Tag

# Compiled regex patterns for performance
_RE_SPACE_BEFORE_NEWLINE = re.compile(r" +\n")
_RE_SPACE_AFTER_NEWLINE = re.compile(r"\n +")

# Assuming logger is configured elsewhere, e.g., in shared/__init__.py
logger = logging.getLogger(__name__)


def parse_homework_html(html: str) -> Dict[str, str]:
    """
    Parse homework HTML response from /i/note.asp into {lesson_id: homework_text} dict.

    Args:
        html: The HTML content string.

    Returns:
        A dictionary mapping the lesson ID to the homework text,
        or an empty dictionary if parsing fails or no homework is found.
    """
    result = {}
    try:
        soup = BeautifulSoup(html, "lxml")

        # 1. Find the hidden input field for LektionsID and extract lesson_id
        lesson_id_input = soup.select_one(
            'input[type="hidden"][id^="LektionsID"]'
        )  # Use CSS selector
        if not lesson_id_input:
            logger.warning("Could not find LektionsID input field in homework HTML.")
            return result

        lesson_id = lesson_id_input.get("value")
        if not lesson_id:
            logger.warning("LektionsID input field found, but has no value.")
            return result

        # 2. Find the <p> tag containing the homework text
        # We locate it by finding the 'Heimaarbeiði' bold tag first
        homework_header = soup.find("b", string="Heimaarbeiði")
        if not homework_header:
            # It might be that there's no homework, which isn't necessarily an error
            logger.info(
                f"No 'Heimaarbeiði' header found for lesson {lesson_id}. Assuming no homework."
            )
            return result  # Return empty dict as no homework text found

        homework_p = homework_header.find_parent("p")
        if not homework_p:
            logger.warning(
                f"Found 'Heimaarbeiði' header but could not find its parent <p> tag for lesson {lesson_id}."
            )
            return result

        # 3. Extract text, converting <br> to \n, <b> to **bold**, <i> to *italic*,
        #    removing header and cleaning whitespace, and preserving literal \n in text nodes.

        def process_node(
            node, is_first_level=False, header_skipped=False, first_br_skipped=False
        ):
            """
            Recursively process a BeautifulSoup node, converting tags to markdown and preserving literal newlines.
            Handles skipping the 'Heimaarbeiði' header and the first <br> after it.
            """
            parts = []
            if isinstance(node, str):
                # Preserve literal \n and decode HTML entities (handled by BS4)
                parts.append(node)
            elif isinstance(node, Tag):
                # Skip the header <b>Heimaarbeiði</b>
                if (
                    is_first_level
                    and not header_skipped
                    and node.name == "b"
                    and node.get_text(strip=True) == "Heimaarbeiði"
                ):
                    return [], True, first_br_skipped  # Skip header, mark as skipped

                # Skip the first <br> immediately after the header
                if (
                    is_first_level
                    and header_skipped
                    and not first_br_skipped
                    and node.name == "br"
                ):
                    return [], header_skipped, True  # Skip first br, mark as skipped

                if node.name == "br":
                    parts.append("\n")
                elif node.name == "b":
                    # Convert <b>...</b> to **...**
                    inner_parts = []
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        inner_parts.extend(child_parts)
                    inner = "".join(inner_parts)
                    if inner.strip():  # Only add if bold tag contains non-whitespace
                        parts.append(f"**{inner.strip()}**")
                elif node.name == "i":
                    # Convert <i>...</i> to *...*
                    inner_parts = []
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        inner_parts.extend(child_parts)
                    inner = "".join(inner_parts)
                    if inner.strip():  # Only add if italic tag contains non-whitespace
                        parts.append(f"*{inner.strip()}*")
                else:
                    # Recursively process children of other tags
                    current_header_skipped = header_skipped
                    current_first_br_skipped = first_br_skipped
                    for child in node.children:
                        (
                            child_parts,
                            current_header_skipped,
                            current_first_br_skipped,
                        ) = process_node(
                            child,
                            False,
                            current_header_skipped,
                            current_first_br_skipped,
                        )
                        parts.extend(child_parts)

            return parts, header_skipped, first_br_skipped

        # Process all direct children of the homework <p> tag
        markdown_parts = []
        final_header_skipped = False
        final_first_br_skipped = False
        for element in homework_p.contents:
            processed_parts, final_header_skipped, final_first_br_skipped = (
                process_node(
                    element, True, final_header_skipped, final_first_br_skipped
                )
            )
            markdown_parts.extend(processed_parts)

        # Join parts and clean final string
        homework_text = "".join(markdown_parts)

        # Clean up whitespace:
        # 1. Remove spaces immediately surrounding newlines
        homework_text = _RE_SPACE_BEFORE_NEWLINE.sub("\n", homework_text)
        homework_text = _RE_SPACE_AFTER_NEWLINE.sub("\n", homework_text)
        # 2. Consolidate multiple newlines into max two (like paragraphs) - Keep single newlines as they are
        # 3. Strip leading/trailing whitespace/newlines from the final string
        homework_text = homework_text.strip()

        # 4. Return data in the expected format
        if homework_text:
            result[lesson_id] = homework_text
        else:
            logger.info(
                f"Found 'Heimaarbeiði' structure but no subsequent text for lesson {lesson_id}."
            )

    except Exception as e:
        # 5. Robust error handling and logging
        logger.error(f"Error parsing homework HTML: {e}", exc_info=True)
        # Return empty dict on any parsing error

    return result
