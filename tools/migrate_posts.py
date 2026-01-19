#!/usr/bin/env python3
"""
Front Matter Migration Script for Chirpy Theme
Converts Minimal Mistakes format to Chirpy format
No external dependencies required
"""

import re
from pathlib import Path

POSTS_DIR = Path("/Users/hanyoung-jeong/Development/blog/_posts")

# Category mapping: old -> new
CATEGORY_MAP = {
    # Spring related
    'jpa': 'Spring',
    'springboot&jpa': 'Spring',
    'spring': 'Spring',
    'querydsl': 'Spring',
    'springstartthere': 'Spring',

    # React/Frontend related
    'front': 'React',
    'react': 'React',
    'js_deepdive': 'React',
    'javascript': 'React',

    # Database related
    'mysql&db': 'Database',
    'mysql': 'Database',
    'sql': 'Database',
    'rdbms': 'Database',
    'rdb': 'Database',

    # Algorithm related
    'boj': 'Algorithm',
    'algorithm': 'Algorithm',
    'algo-programmers': 'Algorithm',
    'programmers': 'Algorithm',

    # Kotlin
    'kotlin': 'Kotlin',

    # DevOps/Blog
    'github&blog': 'DevOps',
    'blog': 'DevOps',
    'network': 'DevOps',
    'english': 'DevOps',
}

# Tag suggestions based on category
TAG_MAP = {
    'Spring': ['spring', 'java', 'backend'],
    'React': ['react', 'javascript', 'frontend'],
    'Database': ['database', 'sql'],
    'Algorithm': ['algorithm', 'problem-solving'],
    'Kotlin': ['kotlin', 'programming'],
    'DevOps': ['devops'],
}

def parse_front_matter_simple(content):
    """Parse YAML front matter using regex (no yaml module needed)"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return None, content

    fm_text = match.group(1)
    body = content[match.end():]

    fm = {}

    # Parse title
    title_match = re.search(r'title:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if title_match:
        fm['title'] = title_match.group(1).strip().strip('"\'')

    # Parse date
    date_match = re.search(r'^date:\s*(.+?)\s*$', fm_text, re.MULTILINE)
    if date_match:
        fm['date'] = date_match.group(1).strip().strip('"\'')

    # Parse categories (list format)
    cat_match = re.search(r'categories:\s*\n\s*-\s*(.+)', fm_text)
    if cat_match:
        fm['categories'] = [cat_match.group(1).strip()]
    else:
        # Single line format
        cat_match = re.search(r'categories:\s*\[?([^\]\n]+)\]?', fm_text)
        if cat_match:
            fm['categories'] = [cat_match.group(1).strip()]

    return fm, body

def get_new_category(old_categories):
    """Map old category to new category"""
    if not old_categories:
        return 'DevOps'

    if isinstance(old_categories, list) and len(old_categories) > 0:
        cat = old_categories[0].lower().strip()
    else:
        cat = str(old_categories).lower().strip()

    return CATEGORY_MAP.get(cat, 'DevOps')

def get_tags(new_category, title):
    """Generate tags based on category and title"""
    tags = set()

    # Add base tags for category
    base_tags = TAG_MAP.get(new_category, [])
    tags.update(base_tags)

    # Add specific tags based on title
    title_lower = title.lower() if title else ''

    if 'jpa' in title_lower:
        tags.add('jpa')
    if 'react' in title_lower:
        tags.add('react')
    if 'kotlin' in title_lower:
        tags.add('kotlin')
    if 'spring' in title_lower:
        tags.add('spring')
    if 'sql' in title_lower or 'mysql' in title_lower:
        tags.add('sql')
    if 'boj' in title_lower or '백준' in title_lower:
        tags.add('boj')
    if 'programmers' in title_lower or '프로그래머스' in title_lower:
        tags.add('programmers')
    if 'javascript' in title_lower or 'js' in title_lower:
        tags.add('javascript')
    if 'querydsl' in title_lower:
        tags.add('querydsl')
    if 'transaction' in title_lower or '트랜잭션' in title_lower:
        tags.add('transaction')

    return list(tags)[:5]  # Max 5 tags

def process_file(filepath):
    """Process a single markdown file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        fm, body = parse_front_matter_simple(content)
        if fm is None:
            print(f"  SKIP (no front matter): {filepath.name}")
            return False

        # Get title
        title = fm.get('title', filepath.stem)

        # Get date from front matter or filename
        date = fm.get('date', '')
        if not date:
            match = re.match(r'(\d{4}-\d{2}-\d{2})', filepath.name)
            if match:
                date = match.group(1)
            else:
                date = '2025-01-01'

        # Clean date string
        date_str = str(date).split()[0].replace('"', '').replace("'", "")

        # Get new category
        old_cat = fm.get('categories', [])
        new_category = get_new_category(old_cat)

        # Get tags
        tags = get_tags(new_category, title)

        # Generate new front matter
        fm_lines = ['---']
        fm_lines.append(f'title: "{title}"')
        fm_lines.append(f'date: {date_str} 09:00:00 +0900')
        fm_lines.append(f'categories: [{new_category}]')
        fm_lines.append(f'tags: [{", ".join(tags)}]')
        fm_lines.append('---')

        new_content = '\n'.join(fm_lines) + '\n' + body

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"  OK: {filepath.name} -> [{new_category}]")
        return True

    except Exception as e:
        print(f"  ERROR: {filepath.name} - {e}")
        return False

def main():
    """Main function"""
    print("=== Front Matter Migration ===\n")

    md_files = list(POSTS_DIR.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files\n")

    success = 0
    failed = 0

    for filepath in sorted(md_files):
        if process_file(filepath):
            success += 1
        else:
            failed += 1

    print(f"\n=== Complete ===")
    print(f"Success: {success}")
    print(f"Failed: {failed}")

if __name__ == "__main__":
    main()
