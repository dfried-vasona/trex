/*
 Itay Marom
 Cisco Systems, Inc.
*/

/*
Copyright (c) 2015-2015 Cisco Systems, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
#include "trex_rpc_cmds.h"
#include <iostream>
#include <sstream>
#include <json/json.h>

using namespace std;

/**
 * add command
 * 
 */
trex_rpc_cmd_rc_e 
TrexRpcCmdTestAdd::_run(const Json::Value &params, Json::Value &result) {

    result["result"] = Json::Value::UInt64(parse_uint64(params, "x", result) + parse_uint64(params, "y", result));
    
    return (TREX_RPC_CMD_OK);
}

/**
 * sub command
 * 
 * @author imarom (16-Aug-15)
 */
trex_rpc_cmd_rc_e 
TrexRpcCmdTestSub::_run(const Json::Value &params, Json::Value &result) {

    result["result"] = Json::Value::UInt64(parse_uint64(params, "x", result) - parse_uint64(params, "y", result));

    return (TREX_RPC_CMD_OK);
}

