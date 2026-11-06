"""Sanitized local configuration checks. No live access/credit/chain claims."""
from .interface_assets import web_assets, InterfaceUnavailable
from importlib.resources import files
import shutil


def readiness(server,*,pdf_available):
    web=web_assets()
    for name in ('product.html','product.js','product.css','docs.html','preview.css','wallet-sdk.js'):
        if not web.joinpath(name).read_bytes():raise ValueError('required preview asset missing')
    reviewers=[]
    for backend in server.backends.values():
        boot=backend.product.bootstrap()
        actor=backend.product.actors.get('typesafe')
        if actor is not None and getattr(actor,'http_client',None)=='curl'and not shutil.which('curl'):
            raise ValueError('configured TypeSafe transport unavailable')
        author=backend.product.author
        author_allowance=author.budget_status()if callable(getattr(author,'budget_status',None))else None
        reviewers.append({'typesafe_configured':actor is not None,
            'operator_allowance':actor.budget_status()if callable(getattr(actor,'budget_status',None))else None,
            'author_configured':boot['routes']['author']['enabled'],
            'author_allowance':author_allowance,
            'near_testnet_configured':backend.product_near.capabilities()['enabled']})
    return {'schema_version':'preview-readiness.v1','configuration_valid':True,
            'reviewer_count':len(reviewers),'https_origin':server.secure_cookie,
            'pdf_export_available':pdf_available,'reviewers':reviewers,
            'inference_verified':False,'provider_requests':0,'chain_requests':0,
            'notes':['No API key, invite, account identity or scenario content is included.',
                     'Local configuration only: catalog access, throughput, external TLS and wallet signature are not verified.',
                     'Operator allowance is conservative dispatch accounting, not a payment or provider billing ledger.']}
