import json
from typing import Dict, List, Any

def create_get_log_page_json() -> Dict[str, Any]:
    """
    Convert NVMe Get Log Page command specification to structured JSON
    for automated test case generation with pynvme
    """
    
    spec = {
        "command": {
            "name": "Get Log Page",
            "opcode": "0x02",
            "type": "admin",
            "section": "5.16",
            "description": "Returns a data buffer containing the log page requested"
        },
        
        "metadata": {
            "spec_version": "2.0a",
            "mandatory": True,
            "affects_ana_state": True,
            "data_transfer": "controller_to_host",
            "command_effects": {
                "namespace_specific": False,
                "changes_state": False
            }
        },
        
        "global_preconditions": [
            {
                "condition": "controller_ready",
                "description": "Controller shall be in ready state (CSTS.RDY = 1)",
                "validation": "check_csts_rdy_bit"
            },
            {
                "condition": "admin_queue_configured",
                "description": "Admin Submission and Completion Queues shall be configured",
                "validation": "check_admin_queues_exist"
            },
            {
                "condition": "identify_controller_complete",
                "description": "Identify Controller command shall have been issued to determine capabilities",
                "validation": "check_controller_capabilities_known"
            }
        ],
        
        "command_structure": {
            "dword0": {
                "name": "CDW0",
                "fields": [
                    {"bits": "7:0", "name": "OPC", "value": "0x02", "description": "Opcode"}
                ]
            },
            
            "dptr": {
                "name": "Data Pointer",
                "dwords": "CDW6-CDW9",
                "bits": "127:0",
                "description": "Specifies the start of the data buffer",
                "reference": "Figure 87",
                "test_values": ["valid_prp", "valid_sgl", "null_pointer", "misaligned"]
            },
            
            "cdw10": {
                "name": "Command Dword 10",
                "fields": [
                    {
                        "bits": "7:0",
                        "name": "LID",
                        "full_name": "Log Page Identifier",
                        "type": "uint8",
                        "mandatory": True,
                        "description": "Specifies the identifier of the log page to retrieve",
                        "test_scenarios": [
                            "mandatory_log_pages",
                            "optional_supported_log_pages",
                            "unsupported_log_page",
                            "reserved_values"
                        ],
                        "expected_behaviors": {
                            "unsupported_lid": "abort_with_invalid_field_in_command"
                        }
                    },
                    {
                        "bits": "14:8",
                        "name": "LSP",
                        "full_name": "Log Specific Field",
                        "type": "uint7",
                        "mandatory": False,
                        "description": "Log page specific field, reserved if not defined for the log page",
                        "test_scenarios": [
                            "zero_when_not_required",
                            "valid_lsp_for_specific_logs",
                            "invalid_lsp_values"
                        ]
                    },
                    {
                        "bits": "15",
                        "name": "RAE",
                        "full_name": "Retain Asynchronous Event",
                        "type": "bool",
                        "mandatory": False,
                        "description": "Specifies when to retain or clear an Asynchronous Event",
                        "values": {
                            "0": "Clear asynchronous event after successful completion",
                            "1": "Retain asynchronous event after successful completion"
                        },
                        "test_scenarios": [
                            "rae_cleared_for_non_aen_logs",
                            "rae_set_for_aen_logs",
                            "verify_event_retention"
                        ]
                    },
                    {
                        "bits": "31:16",
                        "name": "NUMDL",
                        "full_name": "Number of Dwords Lower",
                        "type": "uint16",
                        "mandatory": True,
                        "description": "Least significant 16 bits of the number of dwords to return",
                        "notes": [
                            "Combined with NUMDU forms 0's based value",
                            "If size larger than log page, controller returns complete log page with undefined results beyond"
                        ],
                        "test_scenarios": [
                            "exact_log_page_size",
                            "smaller_than_log_page",
                            "larger_than_log_page",
                            "zero_dwords",
                            "maximum_transfer"
                        ]
                    }
                ]
            },
            
            "cdw11": {
                "name": "Command Dword 11",
                "fields": [
                    {
                        "bits": "15:0",
                        "name": "NUMDU",
                        "full_name": "Number of Dwords Upper",
                        "type": "uint16",
                        "mandatory": True,
                        "description": "Most significant 16 bits of the number of dwords to return",
                        "capability_check": "check_extended_numd_support",
                        "test_scenarios": [
                            "extended_supported_large_transfer",
                            "extended_not_supported_non_zero_numdu"
                        ]
                    },
                    {
                        "bits": "31:16",
                        "name": "LSI",
                        "full_name": "Log Specific Identifier",
                        "type": "uint16",
                        "mandatory": "conditional",
                        "description": "Identifier required for particular log pages",
                        "required_for_logs": [
                            {
                                "lid": "0x05",
                                "name": "Endurance Group Information",
                                "identifier": "Endurance Group Identifier",
                                "reference": "section 3.2.3"
                            },
                            {
                                "lid": "0x0E",
                                "name": "Rotational Media Information",
                                "identifier": "Media Unit Status Domain Identifier",
                                "reference": "section 3.2.4"
                            },
                            {
                                "lid": "0x12",
                                "name": "Predictable Latency Per NVM Set",
                                "identifier": "NVM Set Identifier",
                                "reference": "section 3.2.2"
                            },
                            {
                                "lid": "0x17",
                                "name": "Media Unit Status",
                                "identifier": "Domain Identifier",
                                "reference": "section 3.2.4",
                                "notes": "Reserved if subsystem does not support multiple domains"
                            },
                            {
                                "lid": "0x19",
                                "name": "Supported Capacity Configuration List",
                                "identifier": "Domain Identifier",
                                "reference": "section 3.2.4",
                                "notes": "Reserved if subsystem does not support multiple domains"
                            }
                        ],
                        "test_scenarios": [
                            "valid_identifier_for_required_logs",
                            "invalid_identifier",
                            "zero_when_not_required",
                            "non_zero_domain_not_in_domain_list"
                        ],
                        "expected_behaviors": {
                            "invalid_domain_id": "abort_with_invalid_field_in_command"
                        }
                    }
                ]
            },
            
            "cdw12": {
                "name": "Command Dword 12",
                "fields": [
                    {
                        "bits": "31:0",
                        "name": "LPOL",
                        "full_name": "Log Page Offset Lower",
                        "type": "uint32",
                        "mandatory": "conditional",
                        "description": "Lower 32 bits of offset into the log page",
                        "capability_check": "LPA.bit0",
                        "capability_field": "Identify Controller Data Structure, Log Page Attributes",
                        "test_scenarios": [
                            "offset_supported_byte_offset",
                            "offset_supported_index_offset",
                            "offset_not_supported_non_zero_value"
                        ]
                    }
                ]
            },
            
            "cdw13": {
                "name": "Command Dword 13",
                "fields": [
                    {
                        "bits": "31:0",
                        "name": "LPOU",
                        "full_name": "Log Page Offset Upper",
                        "type": "uint32",
                        "mandatory": "conditional",
                        "description": "Upper 32 bits of offset into the log page",
                        "capability_check": "LPA.bit0"
                    }
                ]
            },
            
            "cdw14": {
                "name": "Command Dword 14",
                "fields": [
                    {
                        "bits": "0",
                        "name": "OT",
                        "full_name": "Offset Type",
                        "type": "bool",
                        "mandatory": "conditional",
                        "description": "Specifies the type of offset",
                        "values": {
                            "0": "Byte offset (mandatory support if LPA.bit0=1)",
                            "1": "Index offset (conditional support based on IOS bit)"
                        },
                        "capability_check": "LPA.bit0 and IOS bit in LID Supported and Effects",
                        "test_scenarios": [
                            "byte_offset_all_logs",
                            "index_offset_ios_set",
                            "index_offset_ios_cleared"
                        ],
                        "expected_behaviors": {
                            "index_offset_ios_cleared": "abort_with_invalid_field_in_command"
                        }
                    },
                    {
                        "bits": "31:1",
                        "name": "Reserved",
                        "type": "reserved",
                        "value": "0x00000000"
                    }
                ]
            }
        },
        
        "test_cases": [
            {
                "id": "TC_GLP_001",
                "name": "Get Mandatory Log Page - Error Information",
                "category": "positive",
                "local_preconditions": [
                    "controller_supports_log_page_lid_0x01"
                ],
                "test_steps": [
                    "Set LID to 0x01 (Error Information)",
                    "Set NUMDL to appropriate size",
                    "Set NUMDU to 0 if extended not supported",
                    "Issue Get Log Page command",
                    "Verify command completes successfully",
                    "Validate returned data structure"
                ],
                "expected_result": "Command completes with status SUCCESS",
                "pynvme_params": {
                    "lid": "0x01",
                    "numdl": 64,
                    "numdu": 0,
                    "rae": 0
                }
            },
            {
                "id": "TC_GLP_002",
                "name": "Get Log Page - Unsupported LID",
                "category": "negative",
                "local_preconditions": [
                    "identify_unsupported_log_page_id"
                ],
                "test_steps": [
                    "Set LID to unsupported value",
                    "Issue Get Log Page command",
                    "Verify command aborted"
                ],
                "expected_result": "Command aborted with Invalid Field in Command",
                "pynvme_params": {
                    "lid": "0xFF",
                    "numdl": 64,
                    "numdu": 0
                },
                "expected_status": {
                    "sct": "0x0",
                    "sc": "0x02"
                }
            },
            {
                "id": "TC_GLP_003",
                "name": "RAE Bit - Clear Asynchronous Event",
                "category": "positive",
                "local_preconditions": [
                    "async_event_pending",
                    "log_page_associated_with_aen"
                ],
                "test_steps": [
                    "Generate AEN condition",
                    "Issue Get Log Page with RAE=0",
                    "Verify event is cleared",
                    "Check AEN is not re-posted"
                ],
                "expected_result": "Event cleared after successful completion",
                "pynvme_params": {
                    "lid": "depends_on_aen",
                    "rae": 0
                }
            },
            {
                "id": "TC_GLP_004",
                "name": "RAE Bit - Retain Asynchronous Event",
                "category": "positive",
                "local_preconditions": [
                    "async_event_pending",
                    "log_page_associated_with_aen"
                ],
                "test_steps": [
                    "Generate AEN condition",
                    "Issue Get Log Page with RAE=1",
                    "Verify event is retained",
                    "Verify AEN can be retrieved again"
                ],
                "expected_result": "Event retained after successful completion",
                "pynvme_params": {
                    "lid": "depends_on_aen",
                    "rae": 1
                }
            },
            {
                "id": "TC_GLP_005",
                "name": "NUMDL/NUMDU - Exact Size Transfer",
                "category": "positive",
                "local_preconditions": [
                    "know_log_page_size"
                ],
                "test_steps": [
                    "Calculate exact dword count for log page",
                    "Set NUMDL and NUMDU to exact size",
                    "Issue Get Log Page command",
                    "Verify complete log page returned"
                ],
                "expected_result": "Exact log page data returned",
                "pynvme_params": {
                    "lid": "0x02",
                    "numdl": "exact_size_lower",
                    "numdu": "exact_size_upper"
                }
            },
            {
                "id": "TC_GLP_006",
                "name": "NUMDL/NUMDU - Larger Than Log Page",
                "category": "boundary",
                "local_preconditions": [
                    "know_log_page_size"
                ],
                "test_steps": [
                    "Set NUMDL/NUMDU larger than log page size",
                    "Issue Get Log Page command",
                    "Verify complete log page returned",
                    "Note: Data beyond log page is undefined"
                ],
                "expected_result": "Complete log page returned, extra data undefined",
                "pynvme_params": {
                    "lid": "0x02",
                    "numdl": "log_size + 1024",
                    "numdu": 0
                }
            },
            {
                "id": "TC_GLP_007",
                "name": "LSI - Endurance Group Identifier",
                "category": "positive",
                "local_preconditions": [
                    "controller_supports_endurance_groups",
                    "valid_endurance_group_exists"
                ],
                "test_steps": [
                    "Set LID to 0x05 (Endurance Group Information)",
                    "Set LSI to valid Endurance Group Identifier",
                    "Issue Get Log Page command",
                    "Verify correct endurance group data returned"
                ],
                "expected_result": "Command completes successfully with correct data",
                "pynvme_params": {
                    "lid": "0x05",
                    "lsi": "valid_eg_id",
                    "numdl": 512
                }
            },
            {
                "id": "TC_GLP_008",
                "name": "LSI - Invalid Domain Identifier",
                "category": "negative",
                "local_preconditions": [
                    "controller_supports_multiple_domains",
                    "domain_list_retrieved"
                ],
                "test_steps": [
                    "Set LID requiring Domain Identifier",
                    "Set LSI to non-existent domain ID",
                    "Issue Get Log Page command",
                    "Verify command aborted"
                ],
                "expected_result": "Command aborted with Invalid Field in Command",
                "pynvme_params": {
                    "lid": "0x17",
                    "lsi": "invalid_domain_id"
                },
                "expected_status": {
                    "sct": "0x0",
                    "sc": "0x02"
                }
            },
            {
                "id": "TC_GLP_009",
                "name": "Log Page Offset - Byte Offset",
                "category": "positive",
                "local_preconditions": [
                    "controller_supports_log_page_offset",
                    "LPA_bit0_set"
                ],
                "test_steps": [
                    "Set LPOL/LPOU to valid byte offset",
                    "Set OT to 0 (byte offset)",
                    "Issue Get Log Page command",
                    "Verify data returned from specified offset"
                ],
                "expected_result": "Log page data from offset returned",
                "pynvme_params": {
                    "lid": "0x02",
                    "lpol": 512,
                    "lpou": 0,
                    "ot": 0
                }
            },
            {
                "id": "TC_GLP_010",
                "name": "Offset Type - Index with IOS Cleared",
                "category": "negative",
                "local_preconditions": [
                    "controller_supports_log_page_offset",
                    "log_page_ios_bit_cleared"
                ],
                "test_steps": [
                    "Set LID where IOS bit is 0",
                    "Set OT to 1 (index offset)",
                    "Issue Get Log Page command",
                    "Verify command aborted"
                ],
                "expected_result": "Command aborted with Invalid Field in Command",
                "pynvme_params": {
                    "lid": "log_with_ios_cleared",
                    "ot": 1
                },
                "expected_status": {
                    "sct": "0x0",
                    "sc": "0x02"
                }
            },
            {
                "id": "TC_GLP_011",
                "name": "Extended NUMD Not Supported",
                "category": "negative",
                "local_preconditions": [
                    "extended_numd_not_supported"
                ],
                "test_steps": [
                    "Verify LPA indicates no extended NUMD support",
                    "Set NUMDU to non-zero value",
                    "Issue Get Log Page command",
                    "Check controller behavior (may ignore or abort)"
                ],
                "expected_result": "Behavior depends on implementation",
                "pynvme_params": {
                    "lid": "0x01",
                    "numdl": 64,
                    "numdu": 1
                }
            }
        ],
        
        "capability_checks": [
            {
                "name": "extended_numd_support",
                "location": "Identify Controller, Log Page Attributes (LPA)",
                "bit": "Extended data supported",
                "affects": ["NUMDU field usage"]
            },
            {
                "name": "log_page_offset_support",
                "location": "Identify Controller, Log Page Attributes (LPA)",
                "bit": "bit 0",
                "affects": ["LPOL, LPOU, OT fields"]
            },
            {
                "name": "ios_bit_check",
                "location": "LID Supported and Effects Data Structure",
                "reference": "Figure 204",
                "affects": ["Index offset support per LID"]
            }
        ],
        
        "error_conditions": [
            {
                "condition": "Unsupported Log Page Identifier",
                "status_code_type": "Generic Command Status",
                "status_code": "Invalid Field in Command (0x02)",
                "sct": "0x0",
                "sc": "0x02"
            },
            {
                "condition": "Index Offset with IOS bit cleared",
                "status_code_type": "Generic Command Status",
                "status_code": "Invalid Field in Command (0x02)",
                "sct": "0x0",
                "sc": "0x02"
            },
            {
                "condition": "Invalid Domain Identifier in LSI",
                "status_code_type": "Generic Command Status",
                "status_code": "Invalid Field in Command (0x02)",
                "sct": "0x0",
                "sc": "0x02"
            },
            {
                "condition": "Data transfer error",
                "status_code_type": "Generic Command Status",
                "status_code": "Data Transfer Error (0x04)",
                "sct": "0x0",
                "sc": "0x04"
            }
        ],
        
        "references": [
            {
                "section": "3.1.2.1.2",
                "description": "Mandatory Log Identifiers - Admin"
            },
            {
                "section": "3.1.2.2.2",
                "description": "Mandatory Log Identifiers - NVM"
            },
            {
                "section": "3.1.2.3.3",
                "description": "Optional Log Identifiers"
            },
            {
                "section": "5.2",
                "description": "Asynchronous Events"
            },
            {
                "section": "8.1.4",
                "description": "ANA state impact"
            },
            {
                "figure": "87",
                "description": "Data Pointer definition"
            },
            {
                "figure": "204",
                "description": "LID Supported and Effects Data Structure"
            }
        ]
    }
    
    return spec


def save_to_json(filename: str = "get_log_page_spec.json"):
    """Save the specification to a JSON file"""
    spec = create_get_log_page_json()
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    print(f"Specification saved to {filename}")
    return spec


def generate_pynvme_test_template(test_case: Dict[str, Any]) -> str:
    """Generate pynvme test code template from test case JSON"""
    
    template = f'''
def test_{test_case['id'].lower()}(nvme0, nvme0n1):
    """
    {test_case['name']}
    Category: {test_case['category']}
    
    Expected Result: {test_case['expected_result']}
    """
    
    # Local preconditions
'''
    
    for precond in test_case.get('local_preconditions', []):
        template += f"    # - {precond}\n"
    
    template += "\n    # Test steps\n"
    for i, step in enumerate(test_case['test_steps'], 1):
        template += f"    # {i}. {step}\n"
    
    # Generate command parameters
    params = test_case.get('pynvme_params', {})
    template += "\n    # Command parameters\n"
    for key, value in params.items():
        if isinstance(value, str):
            template += f"    {key} = {value}\n"
        else:
            template += f"    {key} = {value}\n"
    
    template += '''
    # Allocate buffer
    buf = Buffer(4096)  # Adjust size based on log page
    
    # Issue Get Log Page command
    nvme0.getlogpage(lid, buf, '''
    
    template += f"numdl={params.get('numdl', 64)}"
    if 'rae' in params:
        template += f", rae={params['rae']}"
    if 'lsi' in params:
        template += f", lsi={params['lsi']}"
    
    template += ").waitdone()\n"
    
    # Add status check if it's a negative test
    if 'expected_status' in test_case:
        status = test_case['expected_status']
        template += f'''
    # Verify expected error status
    assert nvme0.status.sct == {status['sct']}
    assert nvme0.status.sc == {status['sc']}
'''
    else:
        template += '''
    # Verify success
    assert nvme0.status == 0
    
    # Validate returned data
    # TODO: Add specific validation based on log page structure
'''
    
    return template


if __name__ == "__main__":
    # Generate and save the JSON specification
    spec = save_to_json()
    
    # Generate sample pynvme test code
    print("\n" + "="*70)
    print("Sample pynvme test code:")
    print("="*70)
    
    # Generate code for first test case
    if spec['test_cases']:
        test_code = generate_pynvme_test_template(spec['test_cases'][0])
        print(test_code)
        
    print("\n" + "="*70)
    print(f"Total test cases defined: {len(spec['test_cases'])}")
    print("="*70)