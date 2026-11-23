"""Editorial instructions for reporting, arguments, analysis, and product documentation."""

import re


# Discovery tags are provisional. The source decides which reading fits.
WRITING = {
    'reporting': (
        'For a news report use thesis for the central event or decision. In reasoning name '
        'who did what, when and where if those details matter. In examples give a concrete '
        'incident, document or interview and say who supplied it. In qualification distinguish '
        'what the reporter established from an allegation, prediction or unresolved question.'
    ),
    'opinion': (
        'For an opinion piece name the writer and the position they defend. Trace the step '
        'from a specific example or stated premise to their conclusion. Attribute objections, '
        'recommendations and predictions to the people making them.'
    ),
    'analysis': (
        'For policy or technology analysis identify the actual rule, proposal or design '
        'decision, who controls it, and who would have to act. Follow one example through '
        'its consequences. Distinguish the policy in force or the feature in use from a '
        'change someone is proposing and from the effects they predict.'
    ),
    'guide': (
        'For a guide identify the reader, the feature or practice and what triggers it. '
        'Trace one supported example from a user action to the visible change, including '
        'any relevant setting, exception or implementation requirement. Keep a documented '
        'capability distinct from a vendor promise or an independently measured outcome.'
    ),
}
GENERAL = (
    'Use the source itself to identify the genre. Give each field a different job. '
    'Use the people, actions, decisions and examples actually in the text. '
    'Omit unsupported details and generic points about the importance of the topic. '
)
CHECKS = {
    'reporting': 'Check who witnessed or said what and the status at the time of reporting.',
    'opinion': 'Check that the position, examples, and counterarguments are attributed to their actual speakers.',
    'analysis': 'Check who has authority, which action is proposed or already in force, and which effects are predictions.',
    'guide': 'Check the documented trigger, available control and resulting behavior; require evidence for any effectiveness claim.',
}


def writing_guidance(genre=''):
    instruction = WRITING.get(genre)
    if instruction:
        return GENERAL + 'When the source fits its provisional genre: ' + instruction
    return GENERAL + (
        'For reporting identify the event and its witnesses. For an argument name the writer, '
        'their reasoning and an example. For a policy proposal identify who would act. For a '
        'guide describe a user action and what the product does in response.'
    )


def verification_guidance(genre=''):
    checks = CHECKS.get(genre) or (
        'Verify attribution, the status of proposed changes, and the difference '
        'between documented capabilities and measured effects.'
    )
    return ('For nonacademic sources check the claim against the genre of the passage. '
            'Reject claims that turn a person’s account or prediction into an established result. '
            + checks)


def distinct_support(reading):
    """A machine-written reading must add information as it moves from claim to example."""
    passages = []
    for key in ('thesis', 'reasoning', 'examples'):
        words = re.findall(r'\w+', str(reading.get(key) or '').casefold())
        if words:
            passages.append(' '.join(words))
    return len(passages) == len(set(passages))
