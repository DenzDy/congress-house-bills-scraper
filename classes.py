class File:
    def __init__(
            self,
            hbn : str,
            main_title : str, 
            session_number : str, 
            significance : str, 
            date_filed : str, 
            principal_authors : str, 
            date_read : str, 
            primary_referral : str, 
            bill_status : str,  
            text_filed : str, 
            is_file_downloadable : str
            ):
        self.hbn = hbn
        self.main_title = main_title
        self.session_number = session_number
        self.significance = significance
        self.date_filed = date_filed
        self.principal_authors = principal_authors
        self.date_read = date_read
        self.primary_referral = primary_referral
        self.bill_status = bill_status
        self.text_filed = text_filed
        self.is_file_downloadable = is_file_downloadable

    def __eq__(self, other):
        if isinstance(other, File):
            print("Collision Check")
            return self.hbn == other.hbn
        return False
    
    def __hash__(self):
        return hash(self.hbn)
files : set[File] = set()