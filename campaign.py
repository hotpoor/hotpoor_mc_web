"""Three Kingdoms-inspired co-op campaign; encounters are game adaptations."""
# Name, outfit colour, helmet colour, beard. Also available as player skins.
CHARACTERS = {
    'zhao-yun': ('赵云', '#c4d4dc', '#a7c7db', False),
    'zhuge-liang': ('诸葛亮', '#dae5db', '#3e5655', True),
    'cao-cao': ('曹操', '#425b8b', '#273550', True),
    'sun-quan': ('孙权', '#973c3b', '#71382c', True),
    'zhou-yu': ('周瑜', '#b34c43', '#d0b073', False),
    'huang-zhong': ('黄忠', '#a08749', '#a58a53', True),
    'ma-chao': ('马超', '#d4d1bd', '#b7ad8e', False),
    'pang-tong': ('庞统', '#7d6652', '#554332', True),
    'lu-su': ('鲁肃', '#6d918a', '#3b605b', True),
    'gan-ning': ('甘宁', '#735c95', '#c4ab66', False),
    'lu-xun': ('陆逊', '#4c867e', '#3a5b58', False),
    'cao-pi': ('曹丕', '#65608d', '#3b3557', False),
    'zhang-jiao': ('张角', '#b6923e', '#f3ce45', True),
    'zhang-bao': ('张宝', '#917442', '#e4b92e', True),
    'zhang-liang': ('张梁', '#967341', '#d9b527', False),
    'dong-zhuo': ('董卓', '#62404c', '#452936', True),
    'hua-xiong': ('华雄', '#76535f', '#54414c', True),
    'yuan-shao': ('袁绍', '#9a8252', '#6c5838', True),
    'yan-liang': ('颜良', '#77814f', '#555e38', True),
    'wen-chou': ('文丑', '#74725e', '#57543e', True),
    'xiahou-dun': ('夏侯惇', '#3d5e83', '#2e405b', True),
    'xiahou-en': ('夏侯恩', '#5e7392', '#3e526d', False),
    'cao-hong': ('曹洪', '#52627e', '#37465e', True),
    'cao-ren': ('曹仁', '#51698e', '#354865', True),
    'zhang-liao': ('张辽', '#4a7881', '#36545a', True),
    'xu-huang': ('徐晃', '#67738e', '#444c64', True),
    'han-xuan': ('韩玄', '#88704f', '#60503b', True),
    'xing-daorong': ('邢道荣', '#82594c', '#5e3d33', True),
    'liu-du': ('刘度', '#7a8260', '#4d563c', True),
    'liu-zhang': ('刘璋', '#84715f', '#5e4c3d', True),
    'zhang-ren': ('张任', '#76876e', '#4f6147', True),
    'yan-yan': ('严颜', '#947854', '#665138', True),
    'xiahou-yuan': ('夏侯渊', '#526d97', '#344962', True),
    'zhang-he': ('张郃', '#5b7392', '#3c4e69', False),
    'zhang-lu': ('张鲁', '#7f6a94', '#544260', True),
    'pang-de': ('庞德', '#76868a', '#4b5a60', True),
    'yu-jin': ('于禁', '#65778d', '#425064', True),
}

# Repeated historical figures are chapter encounters, not claims of historical deaths.
CHAPTERS = [
    ('yellow', '黄巾起义城', 0, -55, '184', '苍天已死，黄天当立。刘关张结义，平定黄巾。',
     ['张角', '张宝', '张梁'], ['刘备', '关羽', '张飞'], ['beam', 'mace', 'hammer']),
    ('hulao', '虎牢讨董城', 55, -55, '190', '诸侯会盟，兵临虎牢，三英战吕布。',
     ['华雄', '吕布', '董卓'], ['刘备', '关羽', '张飞'], ['blade', 'halberd', 'axe']),
    ('guandu', '官渡决战城', 55, 0, '200', '曹袁相争，突袭乌巢，北方格局由此改变。',
     ['颜良', '文丑', '袁绍'], ['曹操', '关羽', '张辽'], ['spear', 'mace', 'bow']),
    ('changban', '长坂突围城', 55, 55, '208', '赵云救主，张飞断桥，护送百姓突围。',
     ['夏侯恩', '曹洪', '夏侯惇'], ['赵云', '张飞', '刘备'], ['sword', 'axe', 'spear']),
    ('chibi', '赤壁鏖战城', 0, 55, '208', '孙刘联军借东风、连环计，火攻破曹军。',
     ['曹仁', '张辽', '徐晃'], ['周瑜', '诸葛亮', '鲁肃'], ['blade', 'halberd', 'hammer']),
    ('jingzhou', '荆州争夺城', -55, 55, '209', '争取荆南四郡，在荆州建立立足之地。',
     ['韩玄', '邢道荣', '刘度'], ['关羽', '黄忠', '鲁肃'], ['bow', 'axe', 'dual']),
    ('yizhou', '益州立业城', -55, 0, '214', '入蜀取益州，建立稳固后方。',
     ['张任', '严颜', '刘璋'], ['刘备', '庞统', '马超'], ['spear', 'blade', 'dual']),
    ('hanzhong', '汉中争雄城', -55, -55, '219', '定军山争锋，夺汉中，进位汉中王。',
     ['夏侯渊', '张郃', '张鲁'], ['黄忠', '赵云', '诸葛亮'], ['bow', 'spear', 'beam']),
    ('fancheng', '樊城风云城', -110, -55, '219', '关羽威震华夏，荆州局势骤变。',
     ['庞德', '于禁', '曹仁'], ['关羽', '甘宁', '陆逊'], ['mace', 'spear', 'blade']),
    ('three', '三分天下城', -110, 0, '220—229', '魏、蜀、吴相继建立。完成三国演武，见证三分天下。',
     ['魏国演武统领', '蜀国演武统领', '吴国演武统领'], ['曹丕', '刘备', '孙权'], ['halberd', 'dual', 'blade']),
]

CITIES = [dict(id=cid, name=name, x=x, z=z, chapter=i + 1, year=year, story=story,
               bosses=bosses, allies=allies, loot=loot)
          for i, (cid, name, x, z, year, story, bosses, allies, loot) in enumerate(CHAPTERS)]

NAME_SKINS = {v[0]: k for k, v in CHARACTERS.items()}
NAME_SKINS.update({'刘备': 'liu-bei', '关羽': 'guan-yu', '张飞': 'zhang-fei', '吕布': 'lu-bu'})


# Only the incoming/outgoing roads get city gates.
for index, city in enumerate(CITIES):
    neighbours = [CITIES[index - 1] if index else {'x': 0, 'z': 0}]
    if index + 1 < len(CITIES):
        neighbours.append(CITIES[index + 1])
    city['gates'] = []
    for other in neighbours:
        dx, dz = other['x'] - city['x'], other['z'] - city['z']
        city['gates'].append(('east' if dx > 0 else 'west') if dx else ('south' if dz > 0 else 'north'))
