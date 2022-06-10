

from DefaultPaths import DefaultPaths


next_generation_id = 0


class Generation(object):
    
    
    def __init__(self, id, prompt, model, sub_model, args):
        self.progress_images = {}
        self.model = model
        self.prompt = prompt
        self.percentage = 0
        self.time_so_far = 0
        
        # set time_left to infinity
        self.time_left = float('inf')
        
        self.args = args
        self.submodel = sub_model
        self.id = id

    def set_status(self, status):
        print(f"{self.id}: {status}")
        self.status = status;

    def done(self, result_image):
        self.result_image = result_image
        self.percentage = 100

    def set_progress(self, percentage, time_so_far, time_left):
        self.percentage = percentage
        self.time_so_far = time_so_far
        self.time_left = time_left

    def latest_progress_image(self):
        return self.progress_images[max(self.progress_images.keys())]

    def save_progress_image(self, image, path=None):
        if path == None:
            path = f'{DefaultPaths.output_path}/{self.id}_{self.percentage}.png'
            
        image.save(path)
        self.progress_images[self.percentage] = path
        self.progress_image = path

    
