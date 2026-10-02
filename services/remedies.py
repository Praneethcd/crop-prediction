"""Disease-specific care and explicitly sourced extension dosage references."""
import re

TOMATO_EARLY='https://agritech.tnau.ac.in/crop_protection/tomato_diseases_2.html'
TOMATO_LATE='https://agritech.tnau.ac.in/crop_protection/tomato_diseases_8.html'
POTATO='https://agritech.tnau.ac.in/horticulture/horti_vegetables_potato.html'
GENERAL='https://ipm.ucanr.edu/agriculture/tomato/'


def canonical_crop(crop):
    key=re.sub(r'[^a-z]','',crop.casefold())
    return {'tomatoes':'Tomato','tomato':'Tomato','potatoes':'Potato','potato':'Potato',
            'pepperbell':'Pepper','bellpepper':'Pepper','capsicum':'Pepper','pepper':'Pepper'}.get(key,crop.strip())


def classify_label(raw):
    label=re.sub(r'_+',' ',raw).strip()
    crop=canonical_crop(label.split()[0])
    disease=label[len(label.split()[0]):].strip()
    if crop=='Pepper':disease=re.sub(r'^bell\s*','',disease,flags=re.I)
    key=disease.casefold()
    severity='none' if key=='healthy' else 'severe' if key=='late blight' else 'moderate'
    return {'crop':crop,'label':crop+' '+disease,'disease':disease,'severity':severity}


def recommendations(label, state='', language='en'):
    crop=canonical_crop(label['crop']);disease=label.get('disease',label['label']).casefold()
    healthy='healthy' in disease
    virus='virus' in disease
    mites='mite' in disease
    if healthy:
        organic=['No disease-specific treatment is indicated. Continue routine inspection.']
        prevention=['Use clean planting material and inspect both sides of leaves weekly.']
    elif virus:
        organic=['There is no spray cure for viral infection. Isolate symptomatic plants and obtain expert confirmation.']
        prevention=['Use certified clean seedlings and disinfect tools between plants.',
                    'For leaf curl, monitor whiteflies; for mosaic, avoid mechanical spread and contaminated tools.']
    elif mites:
        organic=['Inspect leaf undersides for mites and protect beneficial predatory mites.']
        prevention=['Reduce plant stress and avoid excessive dust; seek an integrated pest-management plan.']
    elif 'bacterial' in disease:
        organic=['Remove badly affected material without contaminating healthy plants.']
        prevention=['Use disease-free seedlings; avoid handling wet foliage and overhead irrigation.']
    elif 'late blight' in disease:
        organic=['Separate infected plants and damaged produce. Neem oil is not a proven cure for late blight.']
        prevention=['Improve drainage and reduce prolonged leaf wetness.',
                    'Use clean planting material and inspect neighboring crops promptly.']
    else:
        organic=['Remove affected debris and keep tools clean; seek expert confirmation.']
        prevention=['Rotate crops, improve airflow and water at the roots to reduce leaf wetness.']
    chemicals=[];sources=[]
    if crop=='Tomato' and ('early blight' in disease or 'late blight' in disease):
        source=TOMATO_LATE if 'late blight' in disease else TOMATO_EARLY
        sources=[source]
        chemicals=[{'active_ingredient':'Azoxystrobin','formulation':'23% SC','dose':200,'unit':'ml/acre',
                    'method':'Foliar spray on a growing crop', 'source_url':source,
                    'source_region':'Tamil Nadu, India','source_updated':'2023',
                    'pre_harvest_interval':None,'re_entry_interval':None,
                    'status':'extension_reference_requires_current_product_label'}]
    elif crop=='Potato' and 'blight' in disease:
        sources=[POTATO]
        # The source does not specify concentration; do not silently assign a formulation.
        chemicals=[{'active_ingredient':'Mancozeb','formulation':None,'dose':2,'unit':'g/litre',
                    'method':'Foliar spray on a growing crop','source_url':POTATO,
                    'source_region':'Tamil Nadu, India','source_updated':'2013',
                    'pre_harvest_interval':None,'re_entry_interval':None,
                    'status':'historical_extension_reference_formulation_and_label_required'}]
    elif not healthy:
        sources=[GENERAL] if crop=='Tomato' else []
    status=('No chemical treatment indicated.' if healthy else
            'No chemical spray cures a viral infection.' if virus else
            'Reference doses are not a universal safe prescription. Verify the currently registered product, formulation, water volume, pre-harvest and re-entry intervals with a local agronomist. Never apply field sprays to harvested produce.')
    localized={
        'hi':{'heading':'उपचार और बचाव','notice':'दवा लगाने से पहले स्थानीय विशेषज्ञ से उत्पाद का लेबल, मात्रा और कटाई से पहले की प्रतीक्षा अवधि जाँचें।'},
        'ta':{'heading':'சிகிச்சை மற்றும் தடுப்பு','notice':'மருந்து பயன்படுத்தும் முன் உள்ளூர் நிபுணரிடம் தயாரிப்பு விவரம், அளவு மற்றும் அறுவடைக்கு முந்தைய இடைவெளியைச் சரிபார்க்கவும்.'},
        'en':{'heading':'Treatment and prevention','notice':status}}
    return {'organic':organic,'preventive':prevention,'chemical':chemicals,'dosage_status':status,
            'sources':sources,'region':state or 'India','language':language,
            'localized':localized.get(language,localized['en']),
            'local_match':bool(state and state.casefold().replace(' ','')=='tamilnadu')}
