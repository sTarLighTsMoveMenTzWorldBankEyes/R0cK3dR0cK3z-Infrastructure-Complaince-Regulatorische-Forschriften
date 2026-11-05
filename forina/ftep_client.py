"""Run the local FTEP test protocol with synthetic data, without a server or network."""
import argparse
import json
from pathlib import Path
import tempfile

from .core import Workbench

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional: write public signed test receipt JSON to a new file')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='forina-ftep-demo-') as storage:
        workbench = Workbench(storage)
        org = workbench.add_organization({'name':'Synthetic FTEP demonstration','domain':'example.org','jurisdictions':['EU']})
        enrollment = workbench.enrollment.start({'organization_id':org['id'],'test_consent':True,'authorization_reference':'SYNTHETIC-DEMO-CONSENT'})
        issued = workbench.enrollment.simulate(enrollment['id'], {'fixture':{'name':enrollment['challenge']['dns_name'],'value':enrollment['challenge']['txt_value']}})
        before = workbench.enrollment.verify(issued['receipt'])
        workbench.enrollment.revoke(enrollment['id'], {'reason':'End of local synthetic demonstration'})
        after = workbench.enrollment.verify(issued['receipt'])
        if args.output:
            # Exclusive output: never overwrite a user file or export a private key.
            with args.output.open('x', encoding='utf-8') as target:
                json.dump({'receipt':issued['receipt'],'public_test_key':workbench.enrollment.key_info(),'final_local_status':after}, target, ensure_ascii=False, indent=2)
        print(json.dumps({'profile':'TEST_ONLY','before_revocation':before,'after_revocation':after,'storage':'TEMPORARY_REMOVED_ON_EXIT'},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
