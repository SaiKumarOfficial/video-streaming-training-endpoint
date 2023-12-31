from src.entity.config_entity import TrainingPipelineConfig,DataIngestionConfig,DataValidationConfig,DataPreparationConfig,ModelTrainerConfig, ModelEvaluationConfig, ModelPusherConfig,AnnoyConfig
from src.entity.artifact_entity import DataIngestionArtifact, DataValidationArtifact,DataPreparationArtifact, ModelTrainerArtifact,ModelEvaluationArtifact, ModelPusherArtifact, AnnoyArtifact
from src.components.data_ingestion import DataIngestion
from src.components.data_validation import DataValidation
from src.components.data_preparation import DataPreparation
from src.components.model_trainer import ModelTrainer
from src.components.model_evaluation import ModelEvaluation
from src.components.model_pusher import ModelPusher
from src.components.embeddings import EmbeddingGenerator, VideoFolder
from src.components.nearest_neighbour import Annoy
from src.components.predict import Prediction
from src.constants.training_pipeline import SEQUENCE_LENGTH, IMAGE_HEIGHT,IMAGE_WIDTH
from src.utils.storage_handler import S3Connector
from src.logger import logging
from src.exception import CustomException
from moviepy.editor import VideoFileClip
import os,sys
from tqdm import tqdm
import tensorflow as tf
class TrainPipeline:
    is_pipeline_running = False

    def __init__(self):
        self.training_pipeline_config = TrainingPipelineConfig()

    def start_data_ingestion(self) -> DataIngestionArtifact:
        try:
            self.data_ingestion_config = DataIngestionConfig(self.training_pipeline_config)
            data_ingestion = DataIngestion(self.data_ingestion_config)
            data_ingestion_artifact = data_ingestion.run_step()

            return data_ingestion_artifact

        except Exception as e:
            raise CustomException(e,sys)
        
    def start_data_validation(self, data_ingestion_artifact: DataIngestionArtifact) -> DataValidationArtifact:
        try:
            self.data_validation_config = DataValidationConfig(self.training_pipeline_config)
            data_validation = DataValidation(data_ingestion_artifact= data_ingestion_artifact,
                                             data_validation_config= self.data_validation_config)
            data_validation_artifact = data_validation.run_steps()

            return data_validation_artifact
        except Exception as e:
            raise CustomException(e,sys)

    def start_data_preparation(self, data_validataion_artifact: DataValidationArtifact) -> DataPreparationArtifact:
        try:
            self.data_preparation_config = DataPreparationConfig(self.training_pipeline_config)
            data_preparation = DataPreparation(data_validataion_artifact,
                                                self.data_preparation_config)
            data_preparation_artifact = data_preparation.run_steps()

            return data_preparation_artifact
        except Exception as e:
            raise CustomException(e,sys)
        
    def start_model_training(self, data_preparation_artifact: DataPreparationArtifact,
                             data_validation_artifact: DataValidationArtifact):
        try:
            self.model_training_config = ModelTrainerConfig(self.training_pipeline_config)
            model_training = ModelTrainer(self.model_training_config,
                                          data_validation_artifact,
                                          data_preparation_artifact)
            model_training_artifact = model_training.run_steps()
            return model_training_artifact
        except Exception as e:
            raise CustomException(e,sys)
    
    def start_model_evaluation(self,data_preparation_artifact:DataPreparationArtifact,model_trainer_artifact: ModelTrainerArtifact):
        try:
            self.model_evaluation_config = ModelEvaluationConfig(self.training_pipeline_config)
            model_evaluation = ModelEvaluation(self.model_evaluation_config,
                                               data_preparation_artifact,
                                               model_trainer_artifact)
            model_evaluation_artifact   = model_evaluation.run_steps()
            return model_evaluation_artifact
        except Exception as e:
            raise CustomException(e,sys)
    def start_model_pusher(self,model_evaluation_artifact:ModelEvaluationArtifact):
        try:
            model_pusher_config = ModelPusherConfig(training_pipeline_config= self.training_pipeline_config)
            model_pusher = ModelPusher(model_pusher_config= model_pusher_config,
                                            model_evaluation_artifact= model_evaluation_artifact)
            model_pusher_artifact = model_pusher.run_steps()


            return model_pusher_artifact
        except Exception as e:
            raise CustomException(e,sys)
    
    def generated_embeddings(self, data_validation_artifact: DataValidationArtifact,
                                    model_pusher_artifact: ModelPusherArtifact):
        
        logging.info("Step 1: Load label map and create VideoFolder instance")
        video_folder = VideoFolder(label_map={}, data_validation_artifact= data_validation_artifact)  # Pass your label map here


        logging.info("Step 2: Create DataLoader instance")
        dataloader = tf.data.Dataset.from_generator(
            video_folder.__iter__,
            output_signature=(
                tf.TensorSpec(shape=(SEQUENCE_LENGTH, IMAGE_HEIGHT , IMAGE_WIDTH, 3), dtype=tf.float32),
                tf.TensorSpec(shape=(), dtype=tf.string),
                tf.TensorSpec(shape=(), dtype=tf.string),
            )
        )
        dataloader = dataloader.batch(64).shuffle(buffer_size=1000)

        logging.info("Step 3: Create EmbeddingGenerator instance")
        embeds = EmbeddingGenerator(model_pusher_artifact)

        logging.info("Step 4: Process each batch")

        for batch, values in tqdm(enumerate(dataloader)):
            video_frames, target, link = values

            #Step 5: Run EmbeddingGenerator for the current batch
            result = embeds.run_step(batch, video_frames, target, link)

            # Step 6: Print or handle the response
            print(result)
        return True
    
    
    def create_annoy(self):
        annoy_config = AnnoyConfig(self.training_pipeline_config)
        ann = Annoy(annoy_config)
        annoy_artifact = ann.run_step()
        return annoy_artifact
    
    def start_predictions(self, model_pusher_artifact: ModelPusherArtifact, annoy_artifact: AnnoyArtifact,video_file_path, output_file_path):
        predictions = Prediction( model_pusher_artifact, annoy_artifact)
        resultant_links = predictions.run_predictions(video_file_path,output_file_path)
    
        return resultant_links
    
    def push_artifacts(self, annoy_artifact: AnnoyArtifact, model_pusher_artifact: ModelPusherArtifact):
        connection = S3Connector(annoy_artifact, model_pusher_artifact)
        response = connection.zip_files()

        return response
    
    def run_pipeline(self):
        try:
            logging.info("===============Training Pipleline is start running=============")

            TrainPipeline.is_pipeline_running= True
            data_ingestion_artifact: DataIngestionArtifact = self.start_data_ingestion()
            data_validataion_artifact: DataValidationArtifact  = self.start_data_validation(data_ingestion_artifact)
            data_preparation_artifact: DataPreparationArtifact = self.start_data_preparation(data_validataion_artifact)
            model_training_artifact: ModelTrainerArtifact = self.start_model_training(data_preparation_artifact, data_validataion_artifact)
            model_evaluation_artifact: ModelEvaluationArtifact = self.start_model_evaluation(data_preparation_artifact, model_training_artifact)
            model_pusher_artifact: ModelPusherArtifact = self.start_model_pusher(model_evaluation_artifact)

            self.generated_embeddings(data_validataion_artifact, model_pusher_artifact)
            annoy_artifact = self.create_annoy()
            

            video_file_path = "C:\\Users\\Sheela Sai kumar\\Documents\\ML projects\\video-streaming-training-endpoint\\src\\pipeline\\artifact\\12_26_23_12_06_08\\data_validation\\valid\\IndoorControlRoom\\Video023-Scene-136.mp4"
            output_video_file_path = "C:\\Users\\Sheela Sai kumar\\Documents\\ML projects\\video-streaming-training-endpoint\\test_videos\\output.mp4"


            predicted_videos = self.start_predictions(model_pusher_artifact, annoy_artifact, video_file_path, output_video_file_path)

            print(predicted_videos)

            response = self.push_artifacts(annoy_artifact,model_pusher_artifact)
            print(response)

            # Display the output video.
            # VideoFileClip(output_video_file_path, audio=False, target_resolution=(300,None)).ipython_display()
            
            logging.info("=============Training Pipleline has successfully completed!!!===========")

        except Exception as e:
            raise CustomException(e,sys)
        

if __name__ == "__main__":
    training_pipeline = TrainPipeline()
    training_pipeline.run_pipeline()

