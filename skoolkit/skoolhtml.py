# -*- coding: utf-8 -*-

# Copyright 2008-2014 Richard Dymond (rjdymond@gmail.com)
#
# This file is part of SkoolKit.
#
# SkoolKit is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# SkoolKit is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# SkoolKit. If not, see <http://www.gnu.org/licenses/>.

"""
Defines the :class:`FileInfo` and :class:`HtmlWriter` classes.
"""

import re
import posixpath
import os.path
from os.path import isfile, isdir, basename
import inspect
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from . import VERSION, warn, get_int_param, parse_int, SkoolKitError, SkoolParsingError
from . import skoolmacro
from .image import ImageWriter
from .skoolmacro import MacroParsingError, UnsupportedMacroError
from .skoolparser import TableParser, ListParser, CASE_LOWER
from .refparser import RefParser
from .defaults import REF_FILE

#: The ID of the main disassembly.
MAIN_CODE_ID = 'main'

# Page IDs (as used in the [Paths], [Titles] and [Links] sections)
P_GAME_INDEX = 'GameIndex'
P_MEMORY_MAP = 'MemoryMap'
P_ROUTINES_MAP = 'RoutinesMap'
P_DATA_MAP = 'DataMap'
P_MESSAGES_MAP = 'MessagesMap'
P_UNUSED_MAP = 'UnusedMap'
P_GRAPHICS = 'Graphics'
P_GRAPHIC_GLITCHES = 'GraphicGlitches'
P_GSB = 'GameStatusBuffer'
P_GLOSSARY = 'Glossary'
P_FACTS = 'Facts'
P_BUGS = 'Bugs'
P_POKES = 'Pokes'
P_CHANGELOG = 'Changelog'

# Default image path ID
DEF_IMG_PATH = 'UDGImagePath'

# Byte flip table
FLIP = (
    0, 128, 64, 192, 32, 160, 96, 224, 16, 144, 80, 208, 48, 176, 112, 240, 
    8, 136, 72, 200, 40, 168, 104, 232, 24, 152, 88, 216, 56, 184, 120, 248, 
    4, 132, 68, 196, 36, 164, 100, 228, 20, 148, 84, 212, 52, 180, 116, 244, 
    12, 140, 76, 204, 44, 172, 108, 236, 28, 156, 92, 220, 60, 188, 124, 252, 
    2, 130, 66, 194, 34, 162, 98, 226, 18, 146, 82, 210, 50, 178, 114, 242, 
    10, 138, 74, 202, 42, 170, 106, 234, 26, 154, 90, 218, 58, 186, 122, 250, 
    6, 134, 70, 198, 38, 166, 102, 230, 22, 150, 86, 214, 54, 182, 118, 246, 
    14, 142, 78, 206, 46, 174, 110, 238, 30, 158, 94, 222, 62, 190, 126, 254, 
    1, 129, 65, 193, 33, 161, 97, 225, 17, 145, 81, 209, 49, 177, 113, 241, 
    9, 137, 73, 201, 41, 169, 105, 233, 25, 153, 89, 217, 57, 185, 121, 249, 
    5, 133, 69, 197, 37, 165, 101, 229, 21, 149, 85, 213, 53, 181, 117, 245, 
    13, 141, 77, 205, 45, 173, 109, 237, 29, 157, 93, 221, 61, 189, 125, 253, 
    3, 131, 67, 195, 35, 163, 99, 227, 19, 147, 83, 211, 51, 179, 115, 243, 
    11, 139, 75, 203, 43, 171, 107, 235, 27, 155, 91, 219, 59, 187, 123, 251, 
    7, 135, 71, 199, 39, 167, 103, 231, 23, 151, 87, 215, 55, 183, 119, 247, 
    15, 143, 79, 207, 47, 175, 111, 239, 31, 159, 95, 223, 63, 191, 127, 255
)

def join(*path_components):
    return '/'.join([c for c in path_components if c.replace('/', '')])

class HtmlWriter:
    """Converts a `skool` file and its associated `ref` files to HTML.

    :type skool_parser: :class:`~skoolkit.skoolparser.SkoolParser`
    :param skool_parser: The `skool` file parser to use.
    :type ref_parser: :class:`~skoolkit.refparser.RefParser`
    :param ref_parser: The `ref` file parser to use.
    :type file_info: :class:`FileInfo`
    :param file_info: The `FileInfo` object to use.
    :param case: The case in which to render register names produced by the
                 :ref:`REG` macro (:data:`~skoolkit.skoolparser.CASE_LOWER` for
                 lower case, anything else for upper case)
    :param code_id: The ID of the disassembly.
    """
    def __init__(self, skool_parser, ref_parser, file_info=None, case=None, code_id=MAIN_CODE_ID):
        self.parser = skool_parser
        self.ref_parser = ref_parser
        self.defaults = RefParser()
        self.defaults.parse(StringIO(REF_FILE))
        self.file_info = file_info
        self.case = case
        self.base = skool_parser.base

        colours = self._parse_colours(self.get_dictionary('Colours'))
        iw_options = self.get_dictionary('ImageWriter')
        self.image_writer = ImageWriter(colours, iw_options)
        self.default_image_format = self.image_writer.default_format
        self.frames = {}

        self.snapshot = self.parser.snapshot
        self._snapshots = [(self.snapshot, '')]
        self.entries = self.parser.entries
        self.memory_map = [e for e in self.parser.memory_map if e.ctl != 'i']

        self.table_parser = TableParser()
        self.list_parser = ListParser()
        self._create_macros()

        self.paths = self.get_dictionary('Paths')
        self.titles = self.get_dictionary('Titles')
        links = self.get_dictionary('Links')
        self.page_ids = []
        self.pages = {}
        for page_id, details in self.get_dictionaries('Page'):
            self.page_ids.append(page_id)
            self.pages[page_id] = details
        self.page_contents = {}
        for page_id, page in self.pages.items():
            self.page_contents[page_id] = page.get('PageContent', self.get_section('PageContent:{0}'.format(page_id)))
            path = page.get('Content')
            if path:
                self.page_ids.remove(page_id)
            else:
                path = page['Path']
            self.paths[page_id] = path
            self.titles[page_id] = page.get('Title', page_id)
            links[page_id] = page.get('Link', self.titles[page_id])
        for page_id in links:
            links[page_id] = links[page_id] or self.titles.get(page_id, page_id)
        self.links = self._parse_links(links)

        self.other_code = self.get_dictionaries('OtherCode')
        for c_id, code in self.other_code:
            page_id = code.get('IndexPageId')
            if page_id and page_id not in self.paths:
                self.paths[page_id] = code['Index']

        self.memory_map_names = []
        self.memory_maps = {}
        for map_name, map_details in self.get_dictionaries('MemoryMap'):
            map_details.setdefault('EntryTypes', 'bcgstuwz')
            if self._should_write_map(map_details):
                map_details['Name'] = map_name
                self.memory_maps[map_name] = map_details
                self.memory_map_names.append(map_name)
                self.paths.setdefault(map_name, 'maps/{}.html'.format(map_name))
                self.titles.setdefault(map_name, map_name)

        self.code_path = self.get_code_path(code_id)
        self.game_vars = self.get_dictionary('Game')
        if not self.game_vars['Game']:
            def_game_name = basename(self.parser.skoolfile)
            suffix = '.skool'
            if def_game_name.endswith(suffix):
                def_game_name = def_game_name[:-len(suffix)]
            self.game_vars['Game'] = def_game_name
        self.game_name = self.game_vars['Game']
        self.game = self.game_vars.copy()
        link_operands = self.game_vars['LinkOperands']
        self.link_operands = tuple(op.upper() for op in link_operands.split(','))
        self.js_files = ()
        global_js = self.game_vars['JavaScript']
        if global_js:
            self.js_files = tuple(global_js.split(';'))

        self.bugs = self.get_sections('Bug', True)
        self.facts = self.get_sections('Fact', True)
        self.pokes = self.get_sections('Poke', True)
        self.graphic_glitches = self.get_sections('GraphicGlitch', True)

        self.glossary = []
        for term, paragraphs in self.get_sections('Glossary', True):
            anchor = term.lower().replace(' ', '_')
            self.glossary.append((anchor, term, paragraphs))

        self.graphics = self.get_section('Graphics')
        self.changelog = self._get_changelog()

        self.templates = {}
        for name, template in self.get_sections('Template'):
            self.templates[name] = template
        self.prologue = self.templates['prologue']
        self.html_tag = self.templates['html']
        self.info = self.get_dictionary('Info')
        self.info['Created'] = self.info['Created'].replace('$VERSION', VERSION)
        self.footer = self.format_template('footer')

        self.init()

    def init(self):
        """Perform post-initialisation operations. This method is called after
        `__init__()` has completed. By default the method does nothing, but
        subclasses may override it.
        """
        return

    def warn(self, s):
        warn(s)

    def clone(self, skool_parser, code_id):
        the_clone = self.__class__(skool_parser, self.ref_parser, self.file_info, self.case, code_id)
        the_clone.set_style_sheet(self.game_vars['StyleSheet'])
        return the_clone

    def set_style_sheet(self, value):
        self.game_vars['StyleSheet'] = value

    def _remove_blank_lines(self, html):
        while '\n\n' in html:
            html = html.replace('\n\n', '\n')
        return html

    def format_template(self, template_name, subs=None, trim=False, default=None):
        template = self.templates.get(template_name, self.templates.get(default))
        t_subs = {'Info': self.info}
        t_subs.update(subs or {})
        html = template.format(**t_subs)
        if trim:
            html = self._remove_blank_lines(html)
        return html

    def _parse_colours(self, colour_specs):
        colours = {}
        for k, v in colour_specs.items():
            if v.startswith('#'):
                hex_rgb = v[1:7]
                if len(hex_rgb) == 3:
                    hex_rgb = '{0}{0}{1}{1}{2}{2}'.format(*hex_rgb)
                else:
                    hex_rgb = '0' * (6 - len(hex_rgb)) + hex_rgb
                values = [hex_rgb[i:i + 2] for i in range(0, 5, 2)]
                base = 16
            else:
                values = v.split(',')[:3]
                values.extend(['0'] * (3 - len(values)))
                base = 10
            try:
                colours[k] = tuple([int(n, base) for n in values])
            except ValueError:
                raise SkoolKitError("Invalid colour spec: {}={}".format(k, v))
        return colours

    def _parse_links(self, links):
        new_links = {}
        for page_id, link_text in links.items():
            if link_text.startswith('['):
                sb_count = 1
                index = 1
                length = len(link_text)
                while index < length and sb_count > 0:
                    if link_text[index] == '[':
                        sb_count += 1
                    elif link_text[index] == ']':
                        sb_count -= 1
                    index += 1
                if sb_count == 0:
                    new_links[page_id] = (link_text[1:index - 1], link_text[index:])
            if page_id not in new_links:
                new_links[page_id] = (link_text.strip(), '')
        return new_links

    def get_code_path(self, code_id):
        if code_id.lower() == MAIN_CODE_ID:
            return self.paths.get('CodePath', 'asm')
        for c_id, code in self.other_code:
            if c_id.lower() == code_id.lower():
                return code['Path']

    def has_gbuffer(self):
        return any(entry.ctl == 'g' for entry in self.memory_map)

    def get_dictionary(self, section_name):
        """Return a dictionary built from the contents of a `ref` file section.
        Each line in the section should be of the form ``X=Y``.
        """
        dictionary = self.defaults.get_dictionary(section_name)
        dictionary.update(self.ref_parser.get_dictionary(section_name))
        return dictionary

    def get_dictionaries(self, section_type):
        """Return a list of 2-tuples of the form ``(suffix, dict)`` derived
        from `ref` file sections whose names start with `section_type` followed
        by a colon. ``suffix`` is the part of the section name that follows the
        first colon, and ``dict`` is a dictionary built from the contents of
        that section; each line in the section should be of the form ``X=Y``.
        """
        dictionaries = []
        index = {}
        default_dicts = self.defaults.get_dictionaries(section_type)
        user_dicts = self.ref_parser.get_dictionaries(section_type)
        for suffix, dictionary in default_dicts + user_dicts:
            if suffix in index:
                dictionaries[index[suffix]][1].update(dictionary)
            else:
                index[suffix] = len(dictionaries)
                dictionaries.append((suffix, dictionary))
        return dictionaries

    def get_section(self, section_name, paragraphs=False, lines=False):
        """Return the contents of a `ref` file section.

        :param section_name: The section name.
        :param paragraphs: If `True`, return the contents as a list of
                           paragraphs.
        :param lines: If `True`, return the contents (or each paragraph) as a
                      list of lines; otherwise return the contents (or each
                      paragraph) as a single string.
        """
        if self.ref_parser.has_section(section_name):
            return self.ref_parser.get_section(section_name, paragraphs, lines)
        return self.defaults.get_section(section_name, paragraphs, lines)

    def get_sections(self, section_type, paragraphs=False, lines=False):
        """Return a list of 2-tuples of the form ``(suffix, contents)`` or
        3-tuples of the form ``(infix, suffix, contents)`` derived from
        `ref` file sections whose names start with `section_type` followed by a
        colon. ``suffix`` is the part of the section name that follows either
        the first colon (when there is only one) or the second colon (when
        there is more than one); ``infix`` is the part of the section name
        between the first and second colons (when there is more than one).

        :param section_type: The section name prefix.
        :param paragraphs: If `True`, return the contents of each section as a
                           list of paragraphs.
        :param lines: If `True`, return the contents (or each paragraph) of
                      each section as a list of lines; otherwise return the
                      contents (or each paragraph) as a single string.
        """
        sections = []
        index = {}
        default_sections = self.defaults.get_sections(section_type, paragraphs, lines)
        user_sections = self.ref_parser.get_sections(section_type, paragraphs, lines)
        for section in default_sections + user_sections:
            suffix = ':'.join(section[:-1])
            if suffix in index:
                sections[index[suffix]] = section
            else:
                index[suffix] = len(sections)
                sections.append(section)
        return sections

    def get_entry(self, address):
        """Return the routine or data block that starts at `address`."""
        return self.parser.get_entry(address)

    def get_entry_point_refs(self, address):
        """Return the addresses of the routines and data blocks that contain
        instructions that refer to `address`.
        """
        return self.parser.get_entry_point_refs(address)

    def get_snapshot_name(self):
        """Return the name of the current memory snapshot."""
        return self._snapshots[-1][1]

    def pop_snapshot(self):
        """Discard the current memory snapshot and replace it with the one that
        was most recently saved (by
        :meth:`~skoolkit.skoolhtml.HtmlWriter.push_snapshot`)."""
        self.snapshot = self._snapshots.pop()[0]

    def push_snapshot(self, name=''):
        """Save the current memory snapshot for later retrieval (by
        :meth:`~skoolkit.skoolhtml.HtmlWriter.pop_snapshot`), and put a copy in
        its place.

        :param name: An optional name for the snapshot.
        """
        self._snapshots.append((self.snapshot[:], name))

    def _get_changelog(self):
        changelog = []
        for title, paragraphs in self.get_sections('Changelog', True, True):
            intro = paragraphs[0][0]
            if intro == '-':
                intro = ''
            items = []
            for p in paragraphs[1:]:
                items.append(p)
            changelog.append((title, intro, items))
        return changelog

    def get_page_ids(self):
        return self.page_ids

    def need_image(self, image_path):
        """Return whether an image file needs to be created. This will be true
        only if the file doesn't already exist, or all images are being
        rebuilt. Well-behaved image-creating methods will call this to check
        whether an image file needs to be written, and thus avoid building an
        image when it is not necessary.

        :param image_path: The full path of the image file relative to the root
                           directory of the disassembly.
        """
        return self.file_info.need_image(image_path)

    def file_exists(self, fname):
        return self.file_info.file_exists(fname)

    def join_paragraphs(self, paragraphs, cwd):
        lines = []
        for p in paragraphs:
            lines.append(self.format_template('paragraph', {'paragraph': self.expand(p, cwd).strip()}))
        return '\n'.join(lines)

    def _get_screen_udg(self, row, col, df_addr=16384, af_addr=22528):
        attr = self.snapshot[af_addr + 32 * row + col]
        address = df_addr + 2048 * (row // 8) + 32 * (row % 8) + col
        return Udg(attr, self.snapshot[address:address + 2048:256])

    def screenshot(self, x=0, y=0, w=32, h=24, df_addr=16384, af_addr=22528):
        """Return a two-dimensional array of tiles (instances of
        :class:`~skoolkit.skoolhtml.Udg`) built from the display file and
        attribute file of the current memory snapshot.

        :param x: The x-coordinate of the top-left tile to include (0-31).
        :param y: The y-coordinate of the top-left tile to include (0-23).
        :param w: The width of the array (in tiles).
        :param h: The height of the array (in tiles).
        :param df_addr: The display file address to use.
        :param af_addr: The attribute file address to use.
        """
        width = min((w, 32 - x))
        height = min((h, 24 - y))
        scr_udgs = []
        for r in range(y, y + height):
            scr_udgs.append([self._get_screen_udg(r, c, df_addr, af_addr) for c in range(x, x + width)])
        return scr_udgs

    def flip_udgs(self, udgs, flip=1):
        """Flip a 2D array of UDGs (instances of
        :class:`~skoolkit.skoolhtml.Udg`).

        :param udgs: The array of UDGs.
        :param flip: 1 to flip horizontally, 2 to flip vertically, or 3 to flip
                     horizontally and vertically.
        """
        for row in udgs:
            for udg in row:
                udg.flip(flip)
        if flip & 1:
            for row in udgs:
                row.reverse()
        if flip & 2:
            udgs.reverse()

    def rotate_udgs(self, udgs, rotate=1):
        """Rotate a 2D array of UDGs (instances of
        :class:`~skoolkit.skoolhtml.Udg`) 90 degrees clockwise.

        :param udgs: The array of UDGs.
        :param rotate: The number of rotations to perform.
        """
        for row in udgs:
            for udg in row:
                udg.rotate(rotate)
        if rotate & 3 == 1:
            rotated = []
            for i in range(len(udgs[0])):
                rotated.append([])
                for j in range(len(udgs)):
                    rotated[-1].insert(0, udgs[j][i])
            udgs[:] = rotated
        elif rotate & 3 == 2:
            udgs.reverse()
            for row in udgs:
                row.reverse()
        elif rotate & 3 == 3:
            rotated = []
            for i in range(len(udgs[0])):
                rotated.insert(0, [])
                for j in range(len(udgs)):
                    rotated[0].append(udgs[j][i])
            udgs[:] = rotated

    def get_font_udg_array(self, address, attr, message):
        udgs = []
        for c in message:
            a = address + 8 * (ord(c) - 32)
            udgs.append(Udg(attr, self.snapshot[a:a + 8]))
        return [udgs]

    def write_asm_entries(self):
        self.write_entries(self.code_path, self.paths[P_MEMORY_MAP])

    def write_graphics(self):
        ofile, cwd = self.open_file(self.paths[P_GRAPHICS])
        t_graphics_subs = {'Graphics': self.expand(self.graphics, cwd)}
        ofile.write(self.format_page(P_GRAPHICS, cwd, t_graphics_subs, False))
        ofile.close()

    def write_graphic_glitches(self):
        self._write_box_page(P_GRAPHIC_GLITCHES, self.graphic_glitches)

    def write_index(self):
        ofile, cwd = self.open_file(self.paths[P_GAME_INDEX])

        link_groups = {}
        for section_id, header_text, page_list in self.get_sections('Index', False, True):
            link_groups[section_id] = (header_text, page_list)
        sections = {}
        for section_id, (header_text, page_list) in link_groups.items():
            links = []
            for page_id in page_list:
                fname = self.paths.get(page_id)
                if fname and self.file_exists(fname):
                    link_file = FileInfo.relpath(cwd, fname)
                    link_text = self.links[page_id]
                    links.append((link_file, link_text[0], link_text[1]))
            sections[section_id] = (header_text, links)
        other_code_links = []
        for code_id, code in self.other_code:
            fname = code['Index']
            if self.file_exists(fname):
                link_file = FileInfo.relpath(cwd, fname)
                other_code_links.append((link_file, code.get('Link', code['Title']), ''))
        sections['OtherCode'] = ('Other code', other_code_links)

        t_link_list_subs = {'list_class': 'indexList'}
        sections_html = []
        index = self.get_section('Index', False, True)
        for section_id in index:
            header, links = sections.get(section_id, ('', ()))
            if links:
                link_list = []
                for href, link_text, other_text in links:
                    t_link_list_item_subs = {
                        'href': href,
                        'link_text': link_text,
                        'other_text': other_text
                    }
                    link_list.append(self.format_template('link_list_item', t_link_list_item_subs))
                t_link_list_subs['t_link_list_items'] = '\n'.join(link_list)
                t_index_section_subs = {
                    'header': header,
                    't_link_list': self.format_template('link_list', t_link_list_subs)
                }
                sections_html.append(self.format_template('index_section', t_index_section_subs))

        t_index_subs = {'t_index_sections': '\n'.join(sections_html)}
        ofile.write(self.format_page(P_GAME_INDEX, cwd, t_index_subs))

    def _get_entry_dict(self, cwd, entry):
        desc = ''
        if entry.details:
            desc = self.join_paragraphs(entry.details, cwd)
        return {
            'location': entry.address,
            'address': entry.addr_str,
            'description': desc,
            'url': FileInfo.asm_relpath(cwd, entry.address, self.code_path),
            'size': entry.size,
            'title': self.expand(entry.description, cwd),
        }

    def write_gbuffer(self):
        ofile, cwd = self.open_file(self.paths[P_GSB])
        gsb_includes = [parse_int(a) for a in self.game_vars['GameStatusBufferIncludes'].split(',')]
        gsb_entries = []
        for entry in self.memory_map:
            if not (entry.ctl == 'g' or entry.address in gsb_includes):
                continue
            t_gsb_entry_subs = {'entry': self._get_entry_dict(cwd, entry)}
            gsb_entries.append(self.format_template('gsb_entry', t_gsb_entry_subs))
        ofile.write(self.format_page(P_GSB, cwd, {'t_gsb_entries': '\n'.join(gsb_entries)}))
        ofile.close()

    def format_contents_list(self, link_list):
        items = []
        for anchor, title in link_list:
            item = {'url': '#' + anchor, 'title': title}
            items.append(self.format_template('contents_list_item', {'item': item}))
        t_contents_list_subs = {'t_contents_list_items': '\n'.join(items)}
        return self.format_template('contents_list', t_contents_list_subs)

    def _write_box_page(self, page_id, boxes):
        ofile, cwd = self.open_file(self.paths[page_id])
        boxes_html = []
        for i, (anchor, title, paragraphs) in enumerate(boxes):
            t_box_subs = {
                't_anchor': self.format_anchor(anchor),
                'box_num': 1 + i % 2,
                'title': title,
                'contents': self.join_paragraphs(paragraphs, cwd)
            }
            boxes_html.append(self.format_template('box', t_box_subs))
        t_subs = {
            't_contents_list': self.format_contents_list([(anchor, title) for anchor, title, p in boxes]),
            't_boxes': '\n'.join(boxes_html),
        }
        ofile.write(self.format_page(page_id, cwd, t_subs))
        ofile.close()

    def write_pokes(self):
        self._write_box_page(P_POKES, self.pokes)

    def write_bugs(self):
        self._write_box_page(P_BUGS, self.bugs)

    def write_facts(self):
        self._write_box_page(P_FACTS, self.facts)

    def write_glossary(self):
        self._write_box_page(P_GLOSSARY, self.glossary)

    def _build_changelog_items(self, items, level=0):
        changelog_items = []
        for item, subitems in items:
            if subitems:
                item = '{}\n{}\n'.format(item, self._build_changelog_items(subitems, level + 1))
            changelog_items.append(self.format_template('changelog_item', {'item': item}))
        if level > 0:
            indent = level
        else:
            indent = ''
        t_changelog_item_list_subs = {
            'indent': indent,
            't_changelog_items': '\n'.join(changelog_items)
        }
        return self.format_template('changelog_item_list', t_changelog_item_list_subs)

    def write_changelog(self):
        ofile, cwd = self.open_file(self.paths[P_CHANGELOG])

        contents = []
        entries = []
        for j, (title, description, items) in enumerate(self.changelog):
            contents.append((title, title))
            changelog_items = []
            for item in items:
                indents = [(0, changelog_items)]
                for line in item:
                    subitems = indents[-1][1]
                    item_text = self.expand(line.strip(), cwd)
                    new_indent = len(line) - len(line.lstrip())
                    if new_indent == indents[-1][0]:
                        subitems.append([item_text, None])
                    elif new_indent > indents[-1][0]:
                        new_subitems = [[item_text, None]]
                        subitems[-1][1] = new_subitems
                        indents.append((new_indent, new_subitems))
                    else:
                        while new_indent < indents[-1][0]:
                            indents.pop()
                        subitems = indents[-1][1]
                        subitems.append([item_text, None])
            entry = {
                'title': title,
                'description': description
            }
            t_changelog_entry_subs = {
                't_anchor': self.format_anchor(title),
                'changelog_num': 1 + j % 2,
                'entry': entry,
                't_changelog_item_list': self._build_changelog_items(changelog_items)
            }
            entries.append(self.format_template('changelog_entry', t_changelog_entry_subs))

        t_changelog_subs = {
            't_contents_list': self.format_contents_list(contents),
            't_changelog_entries': '\n'.join(entries),
        }
        ofile.write(self.format_page(P_CHANGELOG, cwd, t_changelog_subs))
        ofile.close()

    def format_registers(self, registers, cwd):
        input_values = []
        output_values = []
        mode = 'I'
        for reg in registers:
            if reg.prefix:
                mode = reg.prefix.upper()[0]
            if mode == 'O':
                output_values.append(reg)
            else:
                input_values.append(reg)

        input_header = self.game_vars['InputRegisterTableHeader']
        output_header = self.game_vars['OutputRegisterTableHeader']
        tables = []
        for template, header, registers in (('input', input_header, input_values), ('output', output_header, output_values)):
            if registers:
                if header:
                    header = self.format_template('registers_header', {'header': header})
                registers_html = []
                for reg in registers:
                    reg.description = self.expand(reg.contents, cwd)
                    t_register_subs = {'register': reg}
                    registers_html.append(self.format_template('register', t_register_subs))
                template_subs = {
                    't_registers_header': header or '',
                    't_registers': '\n'.join(registers_html)
                }
                tables.append(self.format_template(template, template_subs))
            else:
                tables.append('')
        return tables

    def format_entry_comment(self, cwd, colspan, paragraphs, anchor=''):
        t_entry_comment_subs = {
            'colspan': colspan,
            't_anchor': anchor,
            't_paragraphs': self.join_paragraphs(paragraphs, cwd)
        }
        return self.format_template('entry_comment', t_entry_comment_subs)

    def write_entry(self, cwd, entry, fname=None, page_header=None, prev_entry=None, next_entry=None, up=None):
        title_subs = {
            'address': entry.addr_str,
            'label_suffix': ''
        }
        asm_label = self.parser.get_asm_label(entry.address)
        if asm_label:
            title_subs['label_suffix'] = ' ({0})'.format(asm_label)
        if entry.is_routine():
            title_template = 'routine_title'
            page_header_template = 'routine_header'
        elif entry.ctl in 'suz':
            title_template = 'unused_title'
            page_header_template = 'unused_header'
        elif entry.ctl == 'g':
            title_template = 'gsb_title'
            page_header_template = 'gsb_header'
        else:
            title_template = 'data_title'
            page_header_template = 'data_header'
        title = self.format_template(title_template, title_subs)
        page_header = page_header or self.format_template(page_header_template)

        prev_html = up_html = next_html = ''
        if prev_entry:
            t_prev_subs = {
                'href': FileInfo.asm_fname(prev_entry.address),
                'text': prev_entry.addr_str
            }
            prev_html = self.format_template('prev', t_prev_subs)
        if up:
            t_up_subs = {
                'href': '{}#{}'.format(FileInfo.relpath(cwd, up), entry.address)
            }
            up_html = self.format_template('up', t_up_subs)
        if next_entry:
            t_next_subs = {
                'href': FileInfo.asm_fname(next_entry.address),
                'text': next_entry.addr_str
            }
            next_html = self.format_template('next', t_next_subs)
        t_prev_next_subs = {
            't_prev': prev_html,
            't_up': up_html,
            't_next': next_html
        }
        prev_next = self.format_template('prev_next', t_prev_next_subs)

        desc = self.expand(entry.description, cwd)
        label_text = ''
        if asm_label:
            label_text = '{0}: '.format(asm_label)

        table_class = 'disassembly'
        comment_class = 'comment'
        transparent_class = 'transparentComment'
        if entry.ctl not in 'csuz':
            table_class = 'dataDisassembly'
            comment_class = 'dataComment'
            transparent_class = 'transparentDataComment'

        show_comment_col = False
        show_label_col = False
        routine_comment_colspan = 3
        for instruction in entry.instructions:
            if instruction.comment and instruction.comment.text:
                show_comment_col = True
            if instruction.asm_label:
                show_label_col = True
                routine_comment_colspan = 4
            if show_comment_col and show_label_col:
                break

        input_reg, output_reg = self.format_registers(entry.registers, cwd)

        if entry.details:
            entry_details = self.join_paragraphs(entry.details, cwd)
        else:
            entry_details = ''

        lines = []
        for instruction in entry.instructions:
            mid_routine_comments = entry.get_mid_routine_comment(instruction.label)
            address = instruction.address
            anchor = self.format_anchor(address)
            if mid_routine_comments:
                lines.append(self.format_entry_comment(cwd, routine_comment_colspan, mid_routine_comments, anchor))
                anchor = ''

            operation, reference = instruction.operation, instruction.reference
            if reference and operation.upper().startswith(self.link_operands):
                entry_address = reference.entry.address
                if reference.address == entry_address:
                    name = ''
                else:
                    name = '#{0}'.format(reference.address)
                if reference.entry.asm_id:
                    # This is a reference to an entry in another disassembly
                    entry_file = FileInfo.asm_relpath(cwd, entry_address, self.get_code_path(reference.entry.asm_id))
                else:
                    # This is a reference to an entry in the same disassembly
                    entry_file = FileInfo.asm_fname(entry_address)
                link_text = self.parser.get_asm_label(reference.address) or reference.addr_str
                link = self.format_link(entry_file + name, link_text)
                operation = operation.replace(reference.addr_str, link)
            t_instruction_subs = {
                't_asm_label': '',
                'class': 'address',
                't_anchor': anchor,
                'address': instruction.addr_str,
                'instruction': operation,
                't_instruction_comment': ''
            }
            if show_label_col:
                t_instruction_subs['t_asm_label'] = self.format_template('asm_label', {'label': instruction.asm_label or ''})
            if instruction.ctl in 'c*!':
                t_instruction_subs['class'] = 'label'
            t_instruction_comment_subs = None
            if show_comment_col:
                comment = instruction.comment
                if comment:
                    t_instruction_comment_subs = {
                        'class': comment_class,
                        'rowspan': '',
                        'comment': self.expand(comment.text, cwd)
                    }
                    if comment.rowspan > 1:
                        t_instruction_comment_subs['rowspan'] = ' rowspan="{0}"'.format(comment.rowspan)
            else:
                t_instruction_comment_subs = {
                    'class': transparent_class,
                    'rowspan': '',
                    'comment': ''
                }
            if t_instruction_comment_subs:
                t_instruction_subs['t_instruction_comment'] = self.format_template('instruction_comment', t_instruction_comment_subs)
            lines.append(self.format_template('instruction', t_instruction_subs))

        if entry.end_comment:
            lines.append(self.format_entry_comment(cwd, routine_comment_colspan, entry.end_comment))

        instructions_html = '\n'.join(lines)

        t_disassembly_subs = {
            'table_class': table_class,
            'colspan': routine_comment_colspan,
            'entry_details': entry_details,
            't_input': input_reg,
            't_output': output_reg,
            't_instructions': instructions_html
        }
        disassembly = self.format_template('disassembly', t_disassembly_subs)

        t_asm_entry_subs = {
            't_prev_next': prev_next,
            'entry_title': '{}{}: {}'.format(label_text, entry.addr_str, desc),
            't_disassembly': disassembly,
        }

        fname = fname or FileInfo.asm_fname(entry.address)
        with self.file_info.open_file(cwd, fname) as ofile:
            ofile.write(self.format_page('asm_entry', cwd, t_asm_entry_subs, title=title, header=page_header))

    def write_entries(self, cwd, map_file, page_header=None):
        prev_entry = None
        memory_map = self.memory_map
        for i, entry in enumerate(memory_map):
            if i + 1 < len(memory_map):
                next_entry = memory_map[i + 1]
            else:
                next_entry = None
            self.write_entry(cwd, entry, page_header=page_header, prev_entry=prev_entry, next_entry=next_entry, up=map_file)
            prev_entry = entry

    def _should_write_map(self, map_details):
        if map_details.get('Write') == '0':
            return False
        entry_types = map_details['EntryTypes']
        return any(entry.ctl in entry_types for entry in self.memory_map)

    def write_map(self, map_details):
        map_entries = []
        map_name = map_details['Name']
        map_file = self.paths[map_name]
        cwd = os.path.dirname(map_file)
        entry_types = map_details['EntryTypes']
        show_page_byte = map_details.get('PageByteColumns', '0') != '0'
        asm_path = map_details.get('AsmPath', self.code_path)

        for entry in self.memory_map:
            if entry.ctl not in entry_types:
                continue
            purpose = entry.description
            if entry.ctl == 'c':
                entry_class = 'routine'
                desc_class = 'routineDesc'
            elif entry.ctl in 'bw':
                entry_class = 'data'
                desc_class = 'dataDesc'
            elif entry.ctl in 'g':
                entry_class = 'gbuffer'
                desc_class = 'gbufferDesc'
            elif entry.ctl in 'suz':
                if entry.size > 1:
                    suffix = 's'
                else:
                    suffix = ''
                t_map_unused_desc_subs = {'entry': entry, 'suffix': suffix}
                purpose = self.format_template('map_unused_desc', t_map_unused_desc_subs)
                entry_class = 'unused'
                desc_class = 'unusedDesc'
            elif entry.ctl == 't':
                entry_class = 'message'
                desc_class = 'messageDesc'
            address = entry.address
            asm_relpath = FileInfo.relpath(cwd, asm_path)
            asm_file = FileInfo.asm_fname(address, asm_relpath)
            page_byte = ''
            if show_page_byte:
                t_map_page_byte_subs = {'page': address // 256, 'byte': address % 256}
                page_byte = self.format_template('map_page_byte', t_map_page_byte_subs)
            entry.title = self.expand(purpose, cwd)
            t_map_entry_subs = {
                't_map_page_byte': page_byte,
                'class': entry_class,
                'href': asm_file,
                'desc_class': desc_class,
                'entry': entry
            }
            map_entries.append(self.format_template('map_entry', t_map_entry_subs))

        title = self.titles[map_name]
        intro = map_details.get('Intro', '')
        if intro:
            intro = self.format_template('map_intro', {'intro': self.expand(intro, cwd)})
        page_byte_headers = ''
        if show_page_byte:
            page_byte_headers = self.format_template('map_page_byte_header')

        t_map_subs = {
            't_map_intro': intro,
            't_map_page_byte_header': page_byte_headers,
            't_map_entries': '\n'.join(map_entries)
        }
        with self.file_info.open_file(map_file) as ofile:
            ofile.write(self.format_page(map_name, cwd, t_map_subs, default=P_MEMORY_MAP))

    def write_page(self, page_id):
        ofile, cwd = self.open_file(self.paths[page_id])
        page = self.pages[page_id]
        body_class = page.get('BodyClass', '')
        if body_class:
            body_class = ' class="{}"'.format(body_class)
        t_custom_page_subs = {
            'class': body_class,
            'content': self.expand(self.page_contents[page_id], cwd)
        }
        js = page.get('JavaScript')
        ofile.write(self.format_page(page_id, cwd, t_custom_page_subs, trim=False, js=js, default='custom_page'))
        ofile.close()

    def open_file(self, fname):
        ofile = self.file_info.open_file(fname)
        cwd = os.path.dirname(fname)
        return ofile, cwd

    def _set_logo(self, cwd):
        self.game['Logo'] = self.game['LogoImage'] = self._get_logo(cwd)

    def format_page(self, page_id, cwd, subs, trim=True, title=None, header=None, js=None, default=None):
        title = title or self.titles[page_id]
        self._set_logo(cwd)
        subs.update({
            'Game': self.game,
            't_prologue': self.prologue,
            't_html': self.html_tag,
            't_head': self.format_head(cwd, title, js),
            't_header': self.format_header(cwd, header or title),
            't_footer': self.footer
        })
        return self.format_template(page_id, subs, trim, default=default)

    def format_head(self, cwd, title, js=None):
        stylesheets = []
        for css_file in self.game_vars['StyleSheet'].split(';'):
            t_stylesheet_subs = {'href': FileInfo.relpath(cwd, join(self.paths['StyleSheetPath'], basename(css_file)))}
            stylesheets.append(self.format_template('stylesheet', t_stylesheet_subs))
        javascript = []
        js_files = self.js_files
        if js:
            js_files = list(js_files) + js.split(';')
        for js_file in js_files:
            t_javascript_subs = {'src': FileInfo.relpath(cwd, join(self.paths['JavaScriptPath'], basename(js_file)))}
            javascript.append(self.format_template('javascript', t_javascript_subs))

        self._set_logo(cwd)
        t_head_subs = {
            'Game': self.game,
            'title': title,
            't_stylesheets': '\n'.join(stylesheets),
            't_javascripts': '\n'.join(javascript)
        }
        return self.format_template('head', t_head_subs).rstrip()

    def _get_logo(self, cwd):
        logo_macro = self.game_vars['Logo']
        if logo_macro:
            return self.expand(logo_macro, cwd)
        logo_image = self.game_vars['LogoImage']
        if logo_image and self.file_exists(logo_image):
            return self.format_img(self.game_name, FileInfo.relpath(cwd, logo_image))
        return self.game_name

    def format_header(self, cwd, header):
        self._set_logo(cwd)
        t_header_subs = {
            'Game': self.game,
            'href': FileInfo.relpath(cwd, self.paths[P_GAME_INDEX]),
            'header': header
        }
        return self.format_template('header', t_header_subs)

    def format_anchor(self, anchor):
        return self.format_template('anchor', {'anchor': anchor})

    def format_link(self, href, link_text):
        return self.format_template('link', {'href': href, 'link_text': link_text})

    def format_img(self, alt, src):
        return self.format_template('img', {'alt': alt, 'src': src})

    def _get_image_format(self, image_path):
        img_file_ext = image_path.lower()[-4:]
        if img_file_ext == '.png':
            return 'png'
        if img_file_ext == '.gif':
            return 'gif'
        raise SkoolKitError('Unsupported image file format: {}'.format(image_path))

    def write_image(self, image_path, udgs, crop_rect=(), scale=2, mask=False):
        """Create an image and write it to a file.

        :param image_path: The full path of the file to which to write the
                           image (relative to the root directory of the
                           disassembly).
        :param udgs: The two-dimensional array of tiles (instances of
                     :class:`~skoolkit.skoolhtml.Udg`) from which to build the
                     image.
        :param crop_rect: The cropping rectangle, ``(x, y, width, height)``,
                          where ``x`` and ``y`` are the x- and y-coordinates of
                          the top-left pixel to include in the final image, and
                          ``width`` and ``height`` are the width and height of
                          the final image.
        :param scale: The scale of the image.
        :param mask: Whether to apply masks to the tiles in the image.
        """
        frame = Frame(udgs, scale, mask, *crop_rect)
        self.write_animated_image(image_path, [frame])

    def write_animated_image(self, image_path, frames):
        """Create an animated image and write it to a file.

        :param image_path: The full path of the file to which to write the
                           image (relative to the root directory of the
                           disassembly).
        :param frames: A list of the frames (instances of
                       :class:`~skoolkit.skoolhtml.Frame`) from which to build
                       the image.
        """
        img_format = self._get_image_format(image_path)
        f = self.file_info.open_file(image_path, mode='wb')
        self.image_writer.write_image(frames, f, img_format)
        f.close()

    def _create_macros(self):
        self.macros = {}
        prefix = 'expand_'
        for name, method in inspect.getmembers(self, inspect.ismethod):
            search = re.search('{0}[a-z]+'.format(prefix), name)
            if search and name == search.group():
                macro = '#{0}'.format(name[len(prefix):].upper())
                self.macros[macro] = method

    def build_table(self, table):
        table_class = table.table_class
        html = []
        if table_class:
            class_attr = ' class="{0}"'.format(table_class)
        else:
            class_attr = ''
        html.append('<table{0}>'.format(class_attr))
        for row in table.rows:
            html.append('<tr>')
            for cell in row:
                if cell.colspan > 1:
                    colspan = ' colspan="{0}"'.format(cell.colspan)
                else:
                    colspan = ''
                if cell.rowspan > 1:
                    rowspan = ' rowspan="{0}"'.format(cell.rowspan)
                else:
                    rowspan = ''
                if cell.header:
                    tag = 'th'
                    td_class = ''
                else:
                    tag = 'td'
                    cell_class = cell.cell_class
                    if cell.transparent:
                        cell_class += " transparent"
                    cell_class = cell_class.lstrip()
                    if cell_class:
                        td_class = ' class="{0}"'.format(cell_class)
                    else:
                        td_class = ''
                html.append('<{0}{1}{2}{3}>{4}</{0}>'.format(tag, td_class, colspan, rowspan, cell.contents))
            html.append('</tr>')
        html.append('</table>')
        return '\n'.join(html)

    def build_list(self, list_obj):
        html = []
        if list_obj.css_class:
            class_attr = ' class="{0}"'.format(list_obj.css_class)
        else:
            class_attr = ''
        html.append('<ul{0}>'.format(class_attr))
        for item in list_obj.items:
            html.append('<li>{0}</li>'.format(item))
        html.append('</ul>')
        return '\n'.join(html)

    def _get_udg_addresses(self, addr_spec, width):
        if type(addr_spec) is int:
            return [addr_spec]
        num = 1
        addr = addr_spec
        if 'x' in addr:
            addr, num = addr_spec.split('x', 1)
            try:
                num = get_int_param(num)
            except ValueError:
                raise MacroParsingError("Invalid address range specification: {}".format(addr_spec))
        try:
            elements = [get_int_param(n) for n in addr.split('-', 3)]
        except ValueError:
            raise MacroParsingError("Invalid address range specification: {}".format(addr_spec))
        if len(elements) < 2:
            elements.append(elements[0])
        if len(elements) < 3:
            elements.append(1)
        if len(elements) < 4:
            elements.append(elements[2] * width)
        address, end_address, h_step, v_step = elements
        addresses = []
        while address <= end_address:
            addresses.append(address)
            if len(addresses) % width:
                address += h_step
            else:
                address += v_step - (width - 1) * h_step
        return addresses * num

    def img_element(self, cwd, image_path, alt=None):
        """Return an ``<img .../>`` element for an image file.

        :param cwd: The current working directory (from which the relative path
                    of the image file will be computed).
        :param image_path: The full path of the image file relative to the root
                           directory of the disassembly.
        :param alt: The alt text to use for the image; if `None`, the base name
                    of the image file (with the '.png' or '.gif' suffix
                    removed) will be used.
        """
        if alt is None:
            alt = basename(image_path)[:-4]
        return self.format_img(alt, FileInfo.relpath(cwd, image_path))

    def image_path(self, fname, path_id=DEF_IMG_PATH):
        """Return the full path of an image file relative to the root directory
        of the disassembly. If `fname` does not end with '.png' or '.gif', an
        appropriate suffix will be appended (depending on the default image
        format). If `fname` starts with a '/', it will be removed and the
        remainder returned (in which case `path_id` is ignored). If `fname` is
        blank, `None` is returned.

        :param fname: The name of the image file.
        :param path_id: The ID of the target directory (as defined in the
                        :ref:`paths` section of the `ref` file).
        """
        if fname:
            if fname[-4:].lower() in ('.png', '.gif'):
                suffix = ''
            else:
                suffix = '.{0}'.format(self.default_image_format)
            if fname[0] == '/':
                return '{0}{1}'.format(fname[1:], suffix)
            if path_id in self.paths:
                return join(self.paths[path_id], '{0}{1}'.format(fname, suffix))
            raise SkoolKitError("Unknown path ID '{0}' for image file '{1}'".format(path_id, fname))

    def parse_image_params(self, text, index, num=0, defaults=(), path_id=DEF_IMG_PATH, fname='', chars='', ints=None, names=()):
        """Parse a string of the form ``params[{X,Y,W,H}][(fname)]``. The
        parameter string ``params`` may contain comma-separated values and will
        be parsed until either the end is reached, or an invalid character is
        encountered. The default set of valid characters consists of the comma,
        '$', the digits 0-9, and the letters A-F and a-f.

        :param text: The text to parse.
        :param index: The index at which to start parsing.
        :param num: The maximum number of parameters to parse.
        :param defaults: The default values of the optional parameters.
        :param path_id: The ID of the target directory for the image file (as
                        defined in the :ref:`paths` section of the `ref` file).
        :param fname: The default base name of the image file.
        :param chars: Characters to consider valid in addition to those in the
                      default set.
        :param ints: A list of the indexes (0-based) of the parameters that
                     must evaluate to an integer; if `None`, every parameter
                     must evaluate to an integer.
        :return: A list of the form
                 ``[end, image_path, crop_rect, value1, value2...]``, where:

                 * ``end`` is the index at which parsing terminated
                 * ``image_path`` is either the full path of the image file
                   (relative to the root directory of the disassembly) or
                   ``fname`` (if `path_id` is blank or `None`)
                 * ``crop_rect`` is ``(X, Y, W, H)``
                 * ``value1``, ``value2`` etc. are the parameter values
        """
        valid_chars = '$0123456789abcdefABCDEF,' + chars
        if names:
            valid_chars += 'ghijklmnopqrstuvwxyz='
            num = len(names)
        end, param_string, p_text = skoolmacro.parse_params(text, index, only_chars=valid_chars)
        params = skoolmacro.get_params(param_string, num, defaults, ints, names)
        if len(params) > num:
            raise MacroParsingError("Too many parameters (expected {}): '{}'".format(num, text[index:end]))

        if end < len(text) and text[end] == '{':
            end, crop_params = skoolmacro.parse_ints(text, end + 1, defaults=(0, 0, None, None), names=('x', 'y', 'width', 'height'))
            x, y, width, height = crop_params['x'], crop_params['y'], crop_params['width'], crop_params['height']
            end, param_string, p_text = skoolmacro.parse_params(text, end, only_chars='}')
        else:
            x = y = 0
            width = height = None

        if p_text:
            fname = p_text
        if path_id:
            img_path = self.image_path(fname, path_id)
        else:
            img_path = fname

        if names:
            return [end, img_path, (x, y, width, height), params]
        return [end, img_path, (x, y, width, height)] + params

    def _expand_item_macro(self, item, link_text, cwd, items, path_id):
        if item and link_text == '':
            for name, title, contents in items:
                if item == name:
                    link_text = title
                    break
            else:
                raise MacroParsingError("Cannot determine title of item '{}'".format(item))
        href = FileInfo.relpath(cwd, self.paths[path_id])
        if item:
            href += '#' + item
        return self.format_link(href, link_text)

    def expand_bug(self, text, index, cwd):
        end, item, link_text = skoolmacro.parse_bug(text, index)
        return end, self._expand_item_macro(item, link_text, cwd, self.bugs, P_BUGS)

    def expand_call(self, text, index, cwd):
        return skoolmacro.parse_call(text, index, self, cwd)

    def expand_chr(self, text, index, cwd):
        end, num = skoolmacro.parse_chr(text, index)
        return end, '&#{};'.format(num)

    def expand_d(self, text, index, cwd):
        return skoolmacro.parse_d(text, index, self)

    def expand_erefs(self, text, index, cwd):
        return skoolmacro.parse_erefs(text, index, self)

    def expand_fact(self, text, index, cwd):
        end, item, link_text = skoolmacro.parse_fact(text, index)
        return end, self._expand_item_macro(item, link_text, cwd, self.facts, P_FACTS)

    def expand_font(self, text, index, cwd):
        # #FONT[:(text)]addr[,chars,attr,scale][{X,Y,W,H}][(fname)]
        if index < len(text) and text[index] == ':':
            index, message = skoolmacro.get_text_param(text, index + 1)
            if not message:
                raise MacroParsingError("Empty message: {}".format(text[index - 2:index]))
        else:
            message = ''.join([chr(n) for n in range(32, 128)])

        end, img_path, crop_rect, addr, chars, attr, scale = self.parse_image_params(text, index, 4, (len(message), 56, 2), 'FontImagePath', 'font')
        if self.need_image(img_path):
            udg_array = self.get_font_udg_array(addr, attr, message[:chars])
            self.write_image(img_path, udg_array, crop_rect, scale)
        return end, self.img_element(cwd, img_path)

    def expand_html(self, text, index, cwd):
        return skoolmacro.parse_html(text, index)

    def expand_link(self, text, index, cwd):
        end, page_id, anchor, link_text = skoolmacro.parse_link(text, index)
        if page_id not in self.paths:
            raise MacroParsingError("Unknown page ID: {}".format(page_id))
        if link_text == '':
            link_text = self.links[page_id][0]
        href = FileInfo.relpath(cwd, self.paths[page_id]) + anchor
        return end, self.format_link(href, link_text)

    def expand_list(self, text, index, cwd):
        # #LIST[(class)]<items>LIST#
        end, list_obj = self.list_parser.parse_text(text, index)
        return end, self.build_list(list_obj)

    def expand_poke(self, text, index, cwd):
        end, item, link_text = skoolmacro.parse_poke(text, index)
        return end, self._expand_item_macro(item, link_text, cwd, self.pokes, P_POKES)

    def expand_pokes(self, text, index, cwd):
        return skoolmacro.parse_pokes(text, index, self.snapshot)

    def expand_pops(self, text, index, cwd):
        return skoolmacro.parse_pops(text, index, self)

    def expand_pushs(self, text, index, cwd):
        return skoolmacro.parse_pushs(text, index, self)

    def expand_r(self, text, index, cwd):
        end, addr_str, address, code_id, anchor, link_text = skoolmacro.parse_r(text, index)
        if code_id:
            code_path = self.get_code_path(code_id)
            if code_path is None:
                raise MacroParsingError("Could not find code path for '{}' disassembly".format(code_id))
        else:
            code_path = self.code_path
        container = self.parser.get_container(address, code_id)
        if not code_id and not container:
            raise MacroParsingError('Could not find routine file containing {}'.format(addr_str))
        inst_addr_str = self.parser.get_instruction_addr_str(address, code_id)
        if container:
            container_address = container.address
        else:
            container_address = address
        if address != container_address:
            anchor = '#{}'.format(address)
        asm_label = self.parser.get_asm_label(address)
        ref_file = FileInfo.asm_relpath(cwd, container_address, code_path)
        return end, self.format_link(ref_file + anchor, link_text or asm_label or inst_addr_str)

    def expand_refs(self, text, index, cwd):
        return skoolmacro.parse_refs(text, index, self.entries)

    def expand_reg(self, text, index, cwd):
        end, reg = skoolmacro.parse_reg(text, index, self.case == CASE_LOWER)
        return end, self.format_template('reg', {'reg': reg})

    def expand_scr(self, text, index, cwd):
        # #SCR[scale,x,y,w,h,dfAddr,afAddr][{X,Y,W,H}][(fname)]
        end, scr_path, crop_rect, scale, x, y, w, h, df_addr, af_addr = self.parse_image_params(text, index, 7, (1, 0, 0, 32, 24, 16384, 22528), 'ScreenshotImagePath', 'scr')
        if self.need_image(scr_path):
            self.write_image(scr_path, self.screenshot(x, y, w, h, df_addr, af_addr), crop_rect, scale)
        return end, self.img_element(cwd, scr_path)

    def expand_space(self, text, index, cwd):
        end, num_sp = skoolmacro.parse_space(text, index)
        return end, '&#160;' * num_sp

    def expand_table(self, text, index, cwd):
        # #TABLE[(class[,col1class[,col2class...]])]<rows>TABLE#
        end, table = self.table_parser.parse_text(text, index)
        return end, self.build_table(table)

    def expand_udg(self, text, index, cwd):
        # #UDGaddr[,attr,scale,step,inc,flip,rotate,mask][:addr[,step]][{x,y,width,height}][(fname)]
        path_id = 'UDGImagePath'
        param_names = ('addr', 'attr', 'scale', 'step', 'inc', 'flip', 'rotate', 'mask')
        end, udg_path, crop_rect, udg_params = self.parse_image_params(text, index, defaults=(56, 4, 1, 0, 0, 0, 1), path_id=path_id, names=param_names)
        if end < len(text) and text[end] == ':':
            end, udg_path, crop_rect, mask_params = self.parse_image_params(text, end + 1, defaults=(udg_params['step'],), path_id=path_id, names=('addr', 'step'))
        else:
            mask_params = None
        addr, attr, scale = udg_params['addr'], udg_params['attr'], udg_params['scale']
        if udg_path is None:
            udg_path = self.image_path('udg{0}_{1}x{2}'.format(addr, attr, scale))
        if self.need_image(udg_path):
            udg_bytes = [(self.snapshot[addr + n * udg_params['step']] + udg_params['inc']) % 256 for n in range(8)]
            mask_bytes = None
            mask = udg_params['mask']
            if mask and mask_params:
                mask_addr, mask_step = mask_params['addr'], mask_params['step']
                mask_bytes = self.snapshot[mask_addr:mask_addr + 8 * mask_step:mask_step]
            udg = Udg(attr, udg_bytes, mask_bytes)
            udg.flip(udg_params['flip'])
            udg.rotate(udg_params['rotate'])
            self.write_image(udg_path, [[udg]], crop_rect, scale, mask)
        return end, self.img_element(cwd, udg_path)

    def _expand_udgarray_with_frames(self, text, index, cwd):
        end, frame_params, fname = skoolmacro.parse_params(text, index, except_chars=' (')
        if not fname:
            raise MacroParsingError('Missing filename: #UDGARRAY{}'.format(text[index:end]))
        img_path = self.image_path(fname, 'UDGImagePath')
        if self.need_image(img_path):
            frames = []
            default_delay = 32 # 0.32s
            for frame_param in frame_params[1:].split(';'):
                elements = frame_param.rsplit(',', 1)
                if len(elements) == 2:
                    frame_id = elements[0]
                    delay = parse_int(elements[1])
                    if delay is None:
                        raise MacroParsingError('Invalid delay parameter: "{}"'.format(elements[1]))
                    default_delay = delay
                else:
                    frame_id = frame_param
                    delay = default_delay
                if not frame_id:
                    raise MacroParsingError('Missing frame ID: #UDGARRAY{}'.format(text[index:end]))
                try:
                    frame = self.frames[frame_id]
                except KeyError:
                    raise MacroParsingError('No such frame: "{}"'.format(frame_id))
                frame.delay = delay
                frames.append(frame)
            self.write_animated_image(img_path, frames)
        return end, self.img_element(cwd, img_path)

    def expand_udgarray(self, text, index, cwd):
        # #UDGARRAYwidth[,attr,scale,step,inc,flip,rotate,maskType];addr1[,attr1,step1,inc1][:maskAddr1[,maskStep1]];...[{X,Y,W,H}](fname)
        # #UDGARRAY*frame1[,delay1];frame2[,delay2];...(fname)
        if index < len(text) and text[index] == '*':
            return self._expand_udgarray_with_frames(text, index, cwd)

        udg_path_id = None
        end, fname, crop_rect, width, def_attr, scale, def_step, def_inc, flip, rotate, mask_type = self.parse_image_params(text, index, 8, (56, 2, 1, 0, 0, 0, 1), udg_path_id)
        udg_array = [[]]
        has_masks = False
        while end < len(text) and text[end] == ';':
            end, fname, crop_rect, address, attr, step, inc = self.parse_image_params(text, end + 1, 4, (def_attr, def_step, def_inc), udg_path_id, chars='-x', ints=(1, 2, 3))
            udg_addresses = self._get_udg_addresses(address, width)
            mask_addresses = []
            if end < len(text) and text[end] == ':':
                end, fname, crop_rect, mask_addr, mask_step = self.parse_image_params(text, end + 1, 2, (step,), udg_path_id, chars='-x', ints=(1,))
                mask_addresses = self._get_udg_addresses(mask_addr, width)
            has_masks = len(mask_addresses) > 0
            mask_addresses += [None] * (len(udg_addresses) - len(mask_addresses))
            for u, m in zip(udg_addresses, mask_addresses):
                udg_bytes = [(self.snapshot[u + n * step] + inc) % 256 for n in range(8)]
                udg = Udg(attr, udg_bytes)
                if m is not None:
                    udg.mask = [self.snapshot[m + n * mask_step] for n in range(8)]
                if len(udg_array[-1]) == width:
                    udg_array.append([udg])
                else:
                    udg_array[-1].append(udg)
        if not has_masks:
            mask_type = 0

        if not fname:
            raise MacroParsingError('Missing filename: #UDGARRAY{0}'.format(text[index:end]))

        fname, sep, frame = fname.partition('*')
        if sep and not frame:
            frame = fname
        if not fname and not frame:
            raise MacroParsingError('Missing filename or frame ID: #UDGARRAY{}'.format(text[index:end]))

        img_path = self.image_path(fname, 'UDGImagePath')
        need_image = img_path and self.need_image(img_path)
        if frame or need_image:
            if flip:
                self.flip_udgs(udg_array, flip)
            if rotate:
                self.rotate_udgs(udg_array, rotate)
            if frame:
                self.frames[frame] = Frame(udg_array, scale, mask_type, *crop_rect)
            if need_image:
                self.write_image(img_path, udg_array, crop_rect, scale, mask_type)
        if img_path:
            return end, self.img_element(cwd, img_path)
        return end, ''

    def expand_udgtable(self, text, index, cwd):
        return self.expand_table(text, index, cwd)

    def expand(self, text, cwd):
        if not text or text.find('#') < 0:
            return text

        while 1:
            search = re.search('#[A-Z]+', text)
            if not search:
                break
            marker = search.group()
            if not marker in self.macros:
                raise SkoolParsingError('Found unknown macro: {0}'.format(marker))
            repf = self.macros[marker]
            start, index = search.span()
            try:
                end, rep = repf(text, index, cwd)
            except UnsupportedMacroError:
                raise SkoolParsingError('Found unsupported macro: {0}'.format(marker))
            except MacroParsingError as e:
                raise SkoolParsingError('Error while parsing {0} macro: {1}'.format(marker, e.args[0]))
            text = text[:start] + rep + text[end:]

        return text

class FileInfo:
    """Utility class for file-related operations.

    :param topdir: The top-level directory.
    :param game_dir: The subdirectory of `topdir` in which to write all HTML
                     files and image files.
    :param replace_images: Whether existing images should be overwritten.
    """
    def __init__(self, topdir, game_dir, replace_images):
        self.game_dir = game_dir
        self.odir = join(topdir, game_dir)
        self.replace_images = replace_images

    # PY: open_file(self, *names, mode='w') in Python 3
    def open_file(self, *names, **kwargs):
        path = self.odir
        for name in names:
            path = join(path, name)
        if not isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        mode = kwargs.get('mode', 'w') # PY: Not needed in Python 3
        return open(path, mode)

    def need_image(self, image_path):
        return self.replace_images or not self.file_exists(image_path)

    def file_exists(self, fname):
        return isfile(join(self.odir, fname))

    @classmethod
    def relpath(cls, cwd, target):
        return posixpath.relpath(target, cwd)

    @classmethod
    def asm_fname(cls, address, path=''):
        return posixpath.normpath(join(path, '{0}.html'.format(address)))

    @classmethod
    def asm_relpath(cls, cwd, address, path):
        return cls.relpath(cwd, join(path, cls.asm_fname(address)))

class Udg(object):
    """Initialise the UDG.

    :param attr: The attribute byte.
    :param data: The graphic data (sequence of 8 bytes).
    :param mask: The mask data (sequence of 8 bytes).
    """
    def __init__(self, attr, data, mask=None):
        self.attr = attr
        self.data = data
        self.mask = mask

    def __repr__(self):
        if self.mask is None:
            return 'Udg({0}, {1})'.format(self.attr, self.data)
        return 'Udg({0}, {1}, {2})'.format(self.attr, self.data, self.mask)

    def __eq__(self, other):
        if type(other) is Udg:
            return self.attr == other.attr and self.data == other.data and self.mask == other.mask
        return False

    def _rotate_tile(self, tile_data):
        rotated = []
        b = 1
        while b < 129:
            rbyte = 0
            for byte in tile_data:
                rbyte //= 2
                if byte & b:
                    rbyte += 128
            rotated.append(rbyte)
            b *= 2
        rotated.reverse()
        return rotated

    def flip(self, flip=1):
        """Flip the UDG.

        :param flip: 1 to flip horizontally, 2 to flip vertically, or 3 to flip
                     horizontally and vertically.
        """
        if flip & 1:
            for i in range(8):
                self.data[i] = FLIP[self.data[i]]
                if self.mask:
                    self.mask[i] = FLIP[self.mask[i]]
        if flip & 2:
            self.data.reverse()
            if self.mask:
                self.mask.reverse()

    def rotate(self, rotate=1):
        """Rotate the UDG 90 degrees clockwise.

        :param rotate: The number of rotations to perform.
        """
        for i in range(rotate & 3):
            self.data = self._rotate_tile(self.data)
            if self.mask:
                self.mask = self._rotate_tile(self.mask)

    def copy(self):
        if self.mask:
            return Udg(self.attr, self.data[:], self.mask[:])
        return Udg(self.attr, self.data[:])

class Frame(object):
    """Create a frame of an animated image.

    :param udgs: The two-dimensional array of tiles (instances of
                 :class:`~skoolkit.skoolhtml.Udg`) from which to build the
                 frame.
    :param scale: The scale of the frame.
    :param mask: Whether to apply masks to the tiles in the frame.
    :param x: The x-coordinate of the top-left pixel to include in the frame.
    :param y: The y-coordinate of the top-left pixel to include in the frame.
    :param width: The width of the frame; if `None`, the maximum width
                  (derived from `x` and the width of the array of tiles) is
                  used.
    :param height: The height of the frame; if `None`, the maximum height
                   (derived from `y` and the height of the array of tiles) is
                   used.
    :param delay: The delay between this frame and the next in 1/100ths of a
                  second.
    """
    def __init__(self, udgs, scale=1, mask=0, x=0, y=0, width=None, height=None, delay=32):
        self._udgs = udgs
        self._scale = scale
        if mask is False:
            self.mask = 0
        elif mask is True:
            self.mask = 1
        else:
            self.mask = mask
        self._x = x
        self._y = y
        self._full_width = 8 * len(udgs[0]) * scale
        self._full_height = 8 * len(udgs) * scale
        self._width = min(width or self._full_width, self._full_width - x)
        self._height = min(height or self._full_height, self._full_height - y)
        self.delay = delay
        self.trans = 0

    @property
    def udgs(self):
        return self._udgs

    @property
    def scale(self):
        return self._scale

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def cropped(self):
        return self._width != self._full_width or self._height != self._full_height
