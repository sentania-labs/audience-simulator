"""A small general-purpose cast. Meeting context comes from the presenter."""
PEOPLE = [
    ('Morgan', 'CIO', 'Technology priorities, investment and delivery', 'Warm, concise and outcome focused'),
    ('Riley', 'CISO', 'Security, risk and recovery', 'Thoughtful, candid and curious'),
    ('Casey', 'Applications director', 'Applications, integration and user experience', 'Conversational and practical'),
    ('Jordan', 'Platform operator', 'Operations, monitoring and maintenance', 'Direct, relaxed and specific'),
    ('Alex', 'Systems administrator', 'Day-to-day administration and troubleshooting', 'Friendly and hands-on'),
    ('Taylor', 'Infrastructure engineer', 'Infrastructure design, networking and reliability', 'Curious and technically precise'),
]
SCENARIOS = [{
    'id': 'general', 'name': 'General audience', 'background': '', 'source': '',
    'fiction_notice': 'Six fictional colleagues. Add meeting context to give them a shared starting point.',
    'cast': [dict(id=f'general-{i}', name=p[0], role=p[1], expertise=p[2], style=p[3], objective='', history='') for i,p in enumerate(PEOPLE)],
}]


def find_person(cast_id):
    return next((p for s in SCENARIOS for p in s['cast'] if p['id'] == cast_id), None)
