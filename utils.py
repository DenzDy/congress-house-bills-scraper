from classes import File
def json_encoder(obj: File):
    if isinstance(obj, File):
        return {
            'House Bill Number' : obj.hbn,
            'Main Title' : obj.main_title,
            'Session Number' : obj.session_number,
            'Significance' : obj.significance,
            'Date Filed' : obj.date_filed,
            'Principal Authors' : obj.principal_authors,
            'Date Read' : obj.date_read,
            'Primary Referral' : obj.primary_referral,
            'Bill Status' : obj.bill_status,
            'Text Filed' : obj.text_filed
        }
    raise TypeError("Object is not JSON parsable.")