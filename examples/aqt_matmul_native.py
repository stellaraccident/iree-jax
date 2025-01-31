# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test compiling and executing a basic AQT MatMul with IREE."""

from collections import namedtuple
import logging

from iree.jax2.staging_api import *
from iree.jax2.builtins import *

import jax
import jax.numpy as jnp

logging.basicConfig(level=logging.DEBUG)
jax.config.update("jax_enable_mlir", True)


activation_example = jnp.arange(30, dtype=jnp.float32).reshape(5, 6) / 10.4

Params = namedtuple("Params", "weights,activation_scale")
params = Params(
  weights=jnp.arange(18, dtype=jnp.float32).reshape(6, 3) * 500.3,
  activation_scale=jnp.array(5.0),
)

class AqtMatmulModule(StagedModule):

  _params = export_global(params, initialize=True, mutable=False)

  @export_kernel
  def aqt_matmul_native(mdl, params, activation):
    precision = 8
    lower_bound = -2**(precision - 1) + 1
    upper_bound = 2**(precision - 1) - 1

    activation_scaled = activation * params.activation_scale
    activation_rounded = jnp.floor(activation_scaled + jnp.array(0.5))
    activation_clipped = jnp.clip(activation_rounded, lower_bound, upper_bound)
    activation_as_int = activation_clipped.astype(jnp.int8)

    weight_scale = upper_bound / jnp.max(jnp.abs(params.weights))
    weight_scaled = params.weights * weight_scale
    weight_rounded = jnp.floor(weight_scaled + jnp.array(0.5))
    weight_as_int = weight_rounded.astype(jnp.int8)

    scaled_result = jax.lax.dot(
        activation_as_int, weight_as_int, preferred_element_type=jnp.int32)
    return scaled_result / (params.activation_scale * weight_scale)

  @export_traced_proc(signature=(activation_example,))
  def compute_native(mdl, activation):
    return mdl.aqt_matmul_native(mdl._params, activation)


print(get_mlir_module(AqtMatmulModule))
