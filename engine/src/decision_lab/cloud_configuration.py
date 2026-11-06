"""Explicit local Cloud configuration shared by server and preview commands."""
import os
from .env_config import load_env_key
from .near_ai import NearAITextModel


def add_cloud_arguments(parser):
    parser.add_argument('--enable-near-ai',action='store_true',help='Configure NEAR AI Cloud as world author; no request at startup')
    parser.add_argument('--near-ai-api-key-env',default='NEAR_AI_CLOUD_API_KEY',help='Named process/file key; never a raw secret')
    parser.add_argument('--near-ai-env-file',help='Explicit local dotenv file; read only the named key')
    parser.add_argument('--near-ai-model',help='Exact canonical model ID from your Cloud catalog')


def configured_author(args):
    if not (args.enable_near_ai or args.near_ai_env_file):
        if args.near_ai_model:raise ValueError('explicit Cloud opt-in required')
        return None
    model=args.near_ai_model or os.environ.get('NEAR_AI_CLOUD_MODEL','')
    if not model and args.near_ai_env_file:model=load_env_key(args.near_ai_env_file,name='NEAR_AI_CLOUD_MODEL')
    key=load_env_key(args.near_ai_env_file,name=args.near_ai_api_key_env)if args.near_ai_env_file else os.environ.get(args.near_ai_api_key_env,'')
    return NearAITextModel(model=model,api_key=key,timeout_seconds=getattr(args,'model_timeout',180))
